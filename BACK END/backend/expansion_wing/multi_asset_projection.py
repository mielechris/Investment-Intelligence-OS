from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "iios-multi-asset-read-only-projection-v1"
MAX_PAYLOAD_BYTES = 65_536
STATES = {"CURRENT", "AVAILABLE", "AVAILABLE_EMPTY", "STALE", "INCOMPLETE", "UNAVAILABLE", "FAILED_CLOSED"}
LANES = {"us_equities", "equity_etfs", "treasury_rates", "bond_proxies", "commodity_proxies",
    "fx_proxies", "crypto_reference", "listed_options", "intraday", "relative_value"}
AUTHORITY = {"provider_contact":False,"credential_access":False,"automatic_promotion":False,
    "paper_order":False,"ledger_write":False,"broker":False,"live_execution":False}
CANDIDATE_FIELDS = {"candidate_id","instrument_id","asset_lane","originating_scanner","discovered_at",
    "source_cycle_id","completeness","missing_fields","verification_state","promotion_state","blocked_reason"}
TOP_FIELDS = {"schema_version","activation_state","source_generated_at","source_cycle_id",
    "projection_generated_at","evidence_freshness_state","market_session_state","lane_states",
    "candidate_conveyor","professional_observatory","scoreboard","paper_research_sleeves",
    "provider","queue","consolidated_paper_nav","last_trustworthy_hash","authority","projection_hash"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")


def _time(value: Any) -> datetime:
    try: parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError): raise ValueError("PROJECTION_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None: raise ValueError("PROJECTION_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _scalar_dict(value: Any, fields: set[str]) -> bool:
    return isinstance(value,dict) and set(value)==fields and all(not isinstance(x,(dict,list)) for x in value.values())


def build_projection(*, source_generated_at: str, source_cycle_id: str | None,
                     projection_generated_at: str, evidence_freshness_state: str,
                     market_session_state: str, lane_states: dict[str,dict[str,Any]],
                     candidate_conveyor: dict[str,Any], professional_observatory: dict[str,Any],
                     scoreboard: dict[str,Any], paper_research_sleeves: dict[str,Any],
                     provider: dict[str,Any], queue: dict[str,Any], authoritative_paper_nav: float,
                     last_trustworthy_hash: str | None, enabled: bool=False,
                     validation_clock: datetime | None=None) -> dict[str,Any]:
    projection={"schema_version":SCHEMA_VERSION,"activation_state":"ENABLED_READ_ONLY" if enabled else "DISABLED",
        "source_generated_at":source_generated_at,"source_cycle_id":source_cycle_id,
        "projection_generated_at":projection_generated_at,"evidence_freshness_state":evidence_freshness_state,
        "market_session_state":market_session_state,"lane_states":lane_states,
        "candidate_conveyor":candidate_conveyor,"professional_observatory":professional_observatory,
        "scoreboard":scoreboard,"paper_research_sleeves":paper_research_sleeves,"provider":provider,"queue":queue,
        "consolidated_paper_nav":authoritative_paper_nav,"last_trustworthy_hash":last_trustworthy_hash,
        "authority":AUTHORITY.copy()}
    projection["projection_hash"]=hashlib.sha256(_canonical(projection)).hexdigest()
    validate_projection(projection,now=validation_clock)
    return projection


def validate_projection(value: Any, *, now: datetime | None=None) -> None:
    if not isinstance(value,dict) or set(value)!=TOP_FIELDS or value.get("schema_version")!=SCHEMA_VERSION:
        raise ValueError("PROJECTION_SCHEMA_INVALID")
    encoded=_canonical(value)
    if len(encoded)>MAX_PAYLOAD_BYTES: raise ValueError("PROJECTION_TOO_LARGE")
    expected_hash=value.get("projection_hash"); unhashed={k:v for k,v in value.items() if k!="projection_hash"}
    if not re.fullmatch(r"[0-9a-f]{64}",str(expected_hash)) or hashlib.sha256(_canonical(unhashed)).hexdigest()!=expected_hash:
        raise ValueError("PROJECTION_HASH_INVALID")
    source,generated=_time(value["source_generated_at"]),_time(value["projection_generated_at"])
    if source>generated or generated>(now or datetime.now(timezone.utc)).astimezone(timezone.utc):
        raise ValueError("PROJECTION_LOOK_AHEAD_REJECTED")
    if (generated-source).total_seconds()>900 and value["evidence_freshness_state"]=="AVAILABLE":
        raise ValueError("PROJECTION_FRESHNESS_INVALID")
    if (value["source_cycle_id"] is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,120}",str(value["source_cycle_id"]))) or (
            value["last_trustworthy_hash"] is not None and not re.fullmatch(r"[0-9a-f]{64}",str(value["last_trustworthy_hash"]))):
        raise ValueError("PROJECTION_LINEAGE_INVALID")
    if (value["activation_state"] not in {"DISABLED","ENABLED_READ_ONLY"} or
            value["evidence_freshness_state"] not in STATES or
            value["market_session_state"] not in {"PRE_MARKET","REGULAR_SESSION","POST_MARKET",
                "MARKET_CLOSED_WEEKEND","MARKET_CLOSED_HOLIDAY","UNKNOWN"} or
            set(value["lane_states"])!=LANES or any(not isinstance(x,dict) or
                set(x)!={"state","freshness","candidate_count","research_eligible","paper_eligible","missing_evidence","instrument_basis"} or
                x["state"] not in STATES or x["freshness"] not in STATES or
                (x["candidate_count"] is not None and (not isinstance(x["candidate_count"],int) or isinstance(x["candidate_count"],bool) or x["candidate_count"]<0)) or
                not isinstance(x["research_eligible"],bool) or x["paper_eligible"] is not False or
                not isinstance(x["missing_evidence"],str) or x["instrument_basis"] not in {"DIRECT","EXPLICIT_PROXY","REFERENCE_ONLY"}
                for x in value["lane_states"].values())):
        raise ValueError("PROJECTION_STATE_INVALID")
    if any(x["state"] in {"UNAVAILABLE","FAILED_CLOSED"} and x["candidate_count"] is not None for x in value["lane_states"].values()):
        raise ValueError("ABSENT_INFORMATION_NOT_ZERO")
    conveyor=value["candidate_conveyor"]
    if not isinstance(conveyor,dict) or set(conveyor)!={"state","candidates"} or conveyor["state"] not in STATES or not isinstance(conveyor["candidates"],list) or len(conveyor["candidates"])>5:
        raise ValueError("CANDIDATE_CONVEYOR_INVALID")
    for row in conveyor["candidates"]:
        if (not isinstance(row,dict) or set(row)!=CANDIDATE_FIELDS or
                not re.fullmatch(r"candidate_[0-9a-f]{16}",str(row["candidate_id"])) or
                not re.fullmatch(r"[A-Z0-9][A-Z0-9._:/-]{0,79}",str(row["instrument_id"])) or
                row["asset_lane"] not in LANES or row["originating_scanner"]!="EXISTING_IIOS_519_SYMBOL_SCANNER" or
                not isinstance(row["missing_fields"],list) or any(not isinstance(x,str) for x in row["missing_fields"])):
            raise ValueError("CANDIDATE_CONVEYOR_INVALID")
        _time(row["discovered_at"])
        if _time(row["discovered_at"])>source:
            raise ValueError("CANDIDATE_LOOK_AHEAD_REJECTED")
        if not value["source_cycle_id"] or row["source_cycle_id"]!=value["source_cycle_id"]:
            raise ValueError("CANDIDATE_LINEAGE_INVALID")
    if conveyor["state"] in {"FAILED_CLOSED","UNAVAILABLE"} and conveyor["candidates"]:
        raise ValueError("FAILED_CYCLE_CARRY_FORWARD_REJECTED")
    if conveyor["state"]=="AVAILABLE_EMPTY" and conveyor["candidates"] or conveyor["state"]=="AVAILABLE" and not conveyor["candidates"]:
        raise ValueError("CANDIDATE_CONVEYOR_INVALID")
    if value["source_cycle_id"] is None and conveyor["candidates"]:
        raise ValueError("CANDIDATE_LINEAGE_INVALID")
    nested={"professional_observatory":{"state","observation_count","primary_verification_state","agreement_state","sample_warning","endorsement"},
        "scoreboard":{"state","sample_size","unresolved_observations","hit_rate","calibration","return_distribution_state","drawdown_distribution_state","sample_warning","survivorship_warning"},
        "paper_research_sleeves":{"state","sleeve_count","operational_position_count","authoritative_cash","paper_authority","broker_authority"},
        "provider":{"state","confirmed_credits","ambiguous_credits","remaining_ceiling","outbound_requests"},
        "queue":{"state","depth"}}
    for key,fields in nested.items():
        if not _scalar_dict(value[key],fields) or value[key]["state"] not in STATES: raise ValueError("PROJECTION_SECTION_INVALID")
    if (value["professional_observatory"]["endorsement"] is not False or
            value["paper_research_sleeves"]["operational_position_count"]!=0 or
            value["paper_research_sleeves"]["paper_authority"] is not False or
            value["paper_research_sleeves"]["broker_authority"] is not False or
            value["provider"]["outbound_requests"]!=0 or value["consolidated_paper_nav"]!=10_000 or
            value["authority"]!=AUTHORITY or any(value["authority"].values())):
        raise ValueError("PROJECTION_AUTHORITY_INVALID")


class ReadOnlyProjectionReader:
    """Server-configured fixed-file reader; browser input cannot select a path."""
    def __init__(self, root: Path, *, enabled: bool=False, expected_uid: int|None=None,
                 validation_clock: datetime|None=None) -> None:
        self.path=root/"multi-asset-projection.json"; self.enabled=enabled
        self.expected_uid=os.getuid() if expected_uid is None else expected_uid
        self.validation_clock=validation_clock

    def read(self) -> dict[str,Any]:
        if not self.enabled: raise RuntimeError("PROJECTION_READER_DISABLED")
        try: info=self.path.lstat()
        except OSError: raise RuntimeError("PROJECTION_UNAVAILABLE") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_uid!=self.expected_uid or info.st_size>MAX_PAYLOAD_BYTES:
            raise RuntimeError("PROJECTION_UNAVAILABLE")
        try: value=json.loads(self.path.read_bytes())
        except (OSError,json.JSONDecodeError,UnicodeDecodeError): raise RuntimeError("PROJECTION_UNAVAILABLE") from None
        try: validate_projection(value,now=self.validation_clock)
        except ValueError: raise RuntimeError("PROJECTION_UNAVAILABLE") from None
        return value
