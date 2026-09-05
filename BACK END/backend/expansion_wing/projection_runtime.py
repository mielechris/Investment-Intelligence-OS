from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .multi_asset_projection import MAX_PAYLOAD_BYTES, build_projection, validate_projection

ROOT_IDENTIFIER = "EXPANSION_WING_MULTI_ASSET_PROJECTION"
ROOT_DIRECTORY_NAME = "ExpansionWingProjection"
PROJECTION_NAME = "multi-asset-projection.json"
MANIFEST_NAME = "projection-manifest.json"
ROLLBACK_NAME = "rollback-manifest.json"
INVENTORY = frozenset({PROJECTION_NAME, MANIFEST_NAME, ROLLBACK_NAME})
MANIFEST_SCHEMA = "iios-multi-asset-projection-manifest-v1"
ROLLBACK_SCHEMA = "iios-multi-asset-projection-rollback-v1"
MAX_MANIFEST_BYTES = 8_192


def reviewed_projection_root() -> Path:
    """The only source-configured operational root; never accepts browser input."""
    return Path.home() / "Library" / "Application Support" / "IIOS" / ROOT_DIRECTORY_NAME


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError("PROJECTION_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise ValueError("PROJECTION_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _hash(encoded: bytes) -> str:
    return hashlib.sha256(encoded).hexdigest()


def _safe_root(root: Path, *, expected_uid: int, create: bool) -> None:
    if create and not root.exists():
        root.mkdir(mode=0o700, parents=False)
    info = root.lstat()
    if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid or
            stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError("PROJECTION_ROOT_UNSAFE")
    names = {item.name for item in root.iterdir()}
    if names - INVENTORY:
        raise RuntimeError("PROJECTION_INVENTORY_UNSAFE")


def _atomic_write(root: Path, name: str, encoded: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=root)
    temporary_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, root / name)
        directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise RuntimeError("PROJECTION_PUBLICATION_FAILED") from None


def _descriptor_read(root: Path, name: str, *, expected_uid: int, maximum: int) -> bytes:
    directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        except OSError:
            raise RuntimeError("PROJECTION_ARTIFACT_UNSAFE") from None
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > maximum):
                raise RuntimeError("PROJECTION_ARTIFACT_UNSAFE")
            chunks: list[bytes] = []
            remaining = maximum + 1
            while remaining:
                chunk = os.read(fd, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            encoded = b"".join(chunks)
            if len(encoded) > maximum:
                raise RuntimeError("PROJECTION_ARTIFACT_UNSAFE")
            return encoded
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)


def _validate_manifest(value: Any, projection: bytes) -> None:
    fields = {"schema_version", "sequence", "projection_sha256", "projection_size_bytes",
              "generated_at", "source_cycle_id", "root_identifier", "inventory"}
    if (not isinstance(value, dict) or set(value) != fields or value.get("schema_version") != MANIFEST_SCHEMA or
            value.get("root_identifier") != ROOT_IDENTIFIER or value.get("inventory") != sorted(INVENTORY) or
            not isinstance(value.get("sequence"), int) or isinstance(value.get("sequence"), bool) or value["sequence"] < 1 or
            value.get("projection_size_bytes") != len(projection) or value.get("projection_sha256") != _hash(projection) or
            not re.fullmatch(r"[0-9a-f]{64}", str(value.get("projection_sha256")))):
        raise RuntimeError("PROJECTION_MANIFEST_INVALID")
    _timestamp(value.get("generated_at"))
    cycle = value.get("source_cycle_id")
    if cycle is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", str(cycle)):
        raise RuntimeError("PROJECTION_MANIFEST_INVALID")


@dataclass(frozen=True)
class PublicationResult:
    changed: bool
    sequence: int
    projection_sha256: str
    projection_size_bytes: int


class ProjectionStore:
    def __init__(self, root: Path, *, expected_uid: int | None = None) -> None:
        self.root = root
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid

    def create_with_rollback(self, *, generated_at: str) -> None:
        if self.root.exists():
            _safe_root(self.root, expected_uid=self.expected_uid, create=False)
            if ROLLBACK_NAME not in {item.name for item in self.root.iterdir()}:
                raise RuntimeError("ROLLBACK_MANIFEST_MISSING")
            return
        parent = self.root.parent
        parent_info = parent.lstat()
        if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != self.expected_uid:
            raise RuntimeError("PROJECTION_PARENT_UNSAFE")
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        rollback = {"schema_version": ROLLBACK_SCHEMA, "root_identifier": ROOT_IDENTIFIER,
                    "created_at": generated_at, "prior_state": "ABSENT", "created_inventory": sorted(INVENTORY)}
        _atomic_write(self.root, ROLLBACK_NAME, _canonical(rollback))

    def publish(self, projection: dict[str, Any], *, now: datetime | None = None) -> PublicationResult:
        validate_projection(projection, now=now)
        _safe_root(self.root, expected_uid=self.expected_uid, create=False)
        if not (self.root / ROLLBACK_NAME).is_file():
            raise RuntimeError("ROLLBACK_MANIFEST_MISSING")
        encoded = _canonical(projection)
        digest = _hash(encoded)
        sequence = 1
        manifest_path = self.root / MANIFEST_NAME
        if manifest_path.exists():
            previous_projection = _descriptor_read(self.root, PROJECTION_NAME, expected_uid=self.expected_uid,
                                                   maximum=MAX_PAYLOAD_BYTES)
            previous_manifest_raw = _descriptor_read(self.root, MANIFEST_NAME, expected_uid=self.expected_uid,
                                                     maximum=MAX_MANIFEST_BYTES)
            try:
                previous_manifest = json.loads(previous_manifest_raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise RuntimeError("PROJECTION_MANIFEST_INVALID") from None
            _validate_manifest(previous_manifest, previous_projection)
            if _hash(previous_projection) == digest:
                return PublicationResult(False, previous_manifest["sequence"], digest, len(encoded))
            sequence = previous_manifest["sequence"] + 1
        elif (self.root / PROJECTION_NAME).exists():
            raise RuntimeError("PROJECTION_INVENTORY_UNSAFE")
        manifest = {"schema_version": MANIFEST_SCHEMA, "sequence": sequence,
                    "projection_sha256": digest, "projection_size_bytes": len(encoded),
                    "generated_at": projection["projection_generated_at"],
                    "source_cycle_id": projection["source_cycle_id"], "root_identifier": ROOT_IDENTIFIER,
                    "inventory": sorted(INVENTORY)}
        _atomic_write(self.root, PROJECTION_NAME, encoded)
        _atomic_write(self.root, MANIFEST_NAME, _canonical(manifest))
        return PublicationResult(True, sequence, digest, len(encoded))

    def read(self, *, now: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        _safe_root(self.root, expected_uid=self.expected_uid, create=False)
        if {item.name for item in self.root.iterdir()} != INVENTORY:
            raise RuntimeError("PROJECTION_INVENTORY_UNSAFE")
        projection_raw = _descriptor_read(self.root, PROJECTION_NAME, expected_uid=self.expected_uid,
                                          maximum=MAX_PAYLOAD_BYTES)
        manifest_raw = _descriptor_read(self.root, MANIFEST_NAME, expected_uid=self.expected_uid,
                                        maximum=MAX_MANIFEST_BYTES)
        try:
            projection, manifest = json.loads(projection_raw), json.loads(manifest_raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError("PROJECTION_UNAVAILABLE") from None
        _validate_manifest(manifest, projection_raw)
        try:
            validate_projection(projection, now=now)
        except ValueError:
            raise RuntimeError("PROJECTION_UNAVAILABLE") from None
        if projection["projection_hash"] != manifest["projection_sha256"]:
            # The embedded hash intentionally excludes itself; the manifest hashes the exact artifact.
            pass
        if projection["source_cycle_id"] != manifest["source_cycle_id"]:
            raise RuntimeError("PROJECTION_MANIFEST_INVALID")
        return projection, manifest


class FixedProjectionReader:
    def __init__(self, *, enabled: bool = False, root: Path | None = None,
                 expected_uid: int | None = None, validation_clock: datetime | None = None,
                 maximum_age_seconds: int = 900) -> None:
        self.enabled = enabled
        self.root = reviewed_projection_root() if root is None else root
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid
        self.validation_clock = validation_clock
        self.maximum_age_seconds = maximum_age_seconds

    def _validated(self) -> tuple[dict[str, Any], dict[str, Any], bool]:
        if not self.enabled:
            raise RuntimeError("PROJECTION_READER_DISABLED")
        projection, manifest = ProjectionStore(self.root, expected_uid=self.expected_uid).read(now=self.validation_clock)
        clock = (self.validation_clock or datetime.now(timezone.utc)).astimezone(timezone.utc)
        stale = (clock - _timestamp(projection["projection_generated_at"])).total_seconds() > self.maximum_age_seconds
        return projection, manifest, stale

    def read(self) -> dict[str, Any]:
        projection, _, stale = self._validated()
        return _stale_browser_projection(projection, validation_clock=self.validation_clock) if stale else projection

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"publisher_state": "UNAVAILABLE", "reader_state": "DISABLED", "integrity_state": "UNAVAILABLE",
                    "hash_validation": "UNAVAILABLE", "freshness": "UNAVAILABLE", "freshness_state": "UNAVAILABLE",
                    "evidence_current": False, "last_publication_time": None,
                    "source_cycle_id": None, "sequence": None, "root_identifier": ROOT_IDENTIFIER}
        try:
            projection, manifest, stale = self._validated()
        except RuntimeError:
            return {"publisher_state": "UNAVAILABLE", "reader_state": "FAILED_CLOSED", "integrity_state": "INVALID",
                    "hash_validation": "UNAVAILABLE", "freshness": "UNAVAILABLE", "freshness_state": "UNAVAILABLE",
                    "evidence_current": False, "last_publication_time": None,
                    "source_cycle_id": None, "sequence": None, "root_identifier": ROOT_IDENTIFIER}
        freshness = "STALE" if stale else "CURRENT"
        return {"publisher_state": "UNAVAILABLE", "reader_state": "ACTIVE", "integrity_state": "VALID",
                "hash_validation": "VALID", "freshness": freshness, "freshness_state": freshness,
                "evidence_current": not stale,
                "last_publication_time": manifest["generated_at"], "source_cycle_id": manifest["source_cycle_id"],
                "sequence": manifest["sequence"], "root_identifier": ROOT_IDENTIFIER}


def _stale_browser_projection(projection: dict[str, Any], *,
                              validation_clock: datetime | None = None) -> dict[str, Any]:
    """Return a derived, non-persistent view that cannot advance stale evidence."""
    lanes = {name: {"state": "STALE", "freshness": "STALE", "candidate_count": None,
        "research_eligible": False, "paper_eligible": False,
        "missing_evidence": "STALE_EVIDENCE_NOT_CURRENT", "instrument_basis": lane["instrument_basis"]}
        for name, lane in projection["lane_states"].items()}
    paper = projection["paper_research_sleeves"]
    return build_projection(source_generated_at=projection["source_generated_at"],
        source_cycle_id=projection["source_cycle_id"],
        projection_generated_at=projection["projection_generated_at"], evidence_freshness_state="STALE",
        market_session_state=projection["market_session_state"], lane_states=lanes,
        candidate_conveyor={"state": "UNAVAILABLE", "candidates": []},
        professional_observatory={"state": "UNAVAILABLE", "observation_count": None,
            "primary_verification_state": "UNAVAILABLE", "agreement_state": "UNAVAILABLE",
            "sample_warning": True, "endorsement": False},
        scoreboard={"state": "UNAVAILABLE", "sample_size": None, "unresolved_observations": None,
            "hit_rate": None, "calibration": None, "return_distribution_state": "UNAVAILABLE",
            "drawdown_distribution_state": "UNAVAILABLE", "sample_warning": True,
            "survivorship_warning": True},
        paper_research_sleeves={"state": "STALE", "sleeve_count": None,
            "operational_position_count": 0, "authoritative_cash": paper["authoritative_cash"],
            "paper_authority": False, "broker_authority": False},
        provider={"state": "UNAVAILABLE", "confirmed_credits": None, "ambiguous_credits": None,
            "remaining_ceiling": None, "outbound_requests": 0},
        queue={"state": "UNAVAILABLE", "depth": None},
        authoritative_paper_nav=projection["consolidated_paper_nav"],
        last_trustworthy_hash=projection["last_trustworthy_hash"], enabled=True,
        validation_clock=validation_clock or datetime.now(timezone.utc))


def compose_from_sanitized_snapshot(snapshot: dict[str, Any], *, generated_at: str,
                                    market_session_state: str) -> dict[str, Any]:
    """Compose only from an already browser-sanitized snapshot; never opens source evidence."""
    sections = snapshot.get("sections") if isinstance(snapshot, dict) else None
    if not isinstance(sections, dict):
        raise ValueError("SANITIZED_SOURCE_INVALID")
    books = sections.get("books", {}).get("data") if isinstance(sections.get("books"), dict) else None
    radar = sections.get("radar", {}).get("data") if isinstance(sections.get("radar"), dict) else None
    conveyor = sections.get("candidate_conveyor") if isinstance(sections.get("candidate_conveyor"), dict) else None
    if not isinstance(books, dict) or books.get("nav") != 10_000 or books.get("cash") != 10_000 or any(
            books.get(key) != 0 for key in ("positions", "transactions", "orders", "fills")):
        raise ValueError("AUTHORITATIVE_PAPER_BASELINE_INVALID")
    source_generated = snapshot.get("composed_at") or generated_at
    cycle_id = radar.get("candidate_source_cycle_id") if isinstance(radar, dict) else None
    source_hash = radar.get("candidate_source_artifact_hash") if isinstance(radar, dict) else None
    candidates: list[dict[str, Any]] = []
    conveyor_state = "UNAVAILABLE"
    if isinstance(conveyor, dict) and conveyor.get("state") in {"CURRENT", "AVAILABLE", "AVAILABLE_EMPTY"}:
        data = conveyor.get("data")
        rows = data.get("candidates") if isinstance(data, dict) else None
        if isinstance(rows, list) and len(rows) <= 5 and cycle_id and source_hash:
            conveyor_state = "AVAILABLE_EMPTY" if not rows else "AVAILABLE"
            seen: set[str] = set()
            for row in rows:
                if not isinstance(row, dict) or set(row) != {"candidate_id", "ticker", "discovered_at", "missing_fields"}:
                    raise ValueError("CANDIDATE_SOURCE_INVALID")
                if row["candidate_id"] in seen:
                    raise ValueError("CANDIDATE_SOURCE_DUPLICATE")
                seen.add(row["candidate_id"])
                candidates.append({"candidate_id": row["candidate_id"], "instrument_id": row["ticker"],
                    "asset_lane": "us_equities", "originating_scanner": "EXISTING_IIOS_519_SYMBOL_SCANNER",
                    "discovered_at": row["discovered_at"], "source_cycle_id": cycle_id,
                    "completeness": "INCOMPLETE" if row["missing_fields"] else "COMPLETE",
                    "missing_fields": row["missing_fields"], "verification_state": "PRIMARY_SOURCE_REQUIRED",
                    "promotion_state": "BLOCKED", "blocked_reason": "PRIMARY_SOURCE_REQUIRED"})
    lane_states = {name: {"state": "UNAVAILABLE", "freshness": "UNAVAILABLE", "candidate_count": None,
        "research_eligible": False, "paper_eligible": False, "missing_evidence": "CURRENT_LANE_EVIDENCE_UNAVAILABLE",
        "instrument_basis": "REFERENCE_ONLY" if name == "crypto_reference" else
            ("EXPLICIT_PROXY" if name in {"treasury_rates", "bond_proxies", "commodity_proxies", "fx_proxies", "relative_value"} else "DIRECT")}
        for name in ("us_equities", "equity_etfs", "treasury_rates", "bond_proxies", "commodity_proxies",
                     "fx_proxies", "crypto_reference", "listed_options", "intraday", "relative_value")}
    return build_projection(source_generated_at=source_generated, source_cycle_id=cycle_id,
        projection_generated_at=generated_at, evidence_freshness_state="UNAVAILABLE",
        market_session_state=market_session_state, lane_states=lane_states,
        candidate_conveyor={"state": conveyor_state, "candidates": candidates},
        professional_observatory={"state": "UNAVAILABLE", "observation_count": None,
            "primary_verification_state": "UNAVAILABLE", "agreement_state": "UNAVAILABLE",
            "sample_warning": True, "endorsement": False},
        scoreboard={"state": "UNAVAILABLE", "sample_size": None, "unresolved_observations": None,
            "hit_rate": None, "calibration": None, "return_distribution_state": "UNAVAILABLE",
            "drawdown_distribution_state": "UNAVAILABLE", "sample_warning": True, "survivorship_warning": True},
        paper_research_sleeves={"state": "AVAILABLE_EMPTY", "sleeve_count": 0,
            "operational_position_count": 0, "authoritative_cash": books["cash"],
            "paper_authority": False, "broker_authority": False},
        provider={"state": "UNAVAILABLE", "confirmed_credits": None, "ambiguous_credits": None,
            "remaining_ceiling": None, "outbound_requests": 0},
        queue={"state": "UNAVAILABLE", "depth": None}, authoritative_paper_nav=books["nav"],
        last_trustworthy_hash=source_hash, enabled=True, validation_clock=_timestamp(generated_at))
