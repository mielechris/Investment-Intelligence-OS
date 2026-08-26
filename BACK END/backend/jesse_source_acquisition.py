from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException

from institutional_research_intelligence import SOURCE_REGISTRY, ingest_report
from ledger import latest_object, record_event, record_object, utc_now
from macro_policy_intelligence import build_monetary_policy_snapshot
from provider_hardening import GENERIC_USER_AGENT, fetch_google_news_rss

router = APIRouter()
SOURCE_CASE = "jesse_source_acquisition"
UNIVERSE_ID = "governed_dislocation_universe"
UNIVERSE_TYPE = "governed_dislocation_universe"

DEFAULT_INBOX = Path(__file__).resolve().parent / "authorized_research_inbox"
DEFAULT_PROCESSED = Path(__file__).resolve().parent / "authorized_research_processed"
DEFAULT_FED_FILE = Path(__file__).resolve().parent / "fed_probability_input.json"


def _institution_name(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("institution") or "").strip()
    return str(row or "").strip()


def normalize_universe(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("symbols must be a list")
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = str(value or "").strip().upper()
        if symbol.endswith(".US"):
            symbol = symbol[:-3]
        if not symbol or len(symbol) > 12:
            continue
        if not all(ch.isalnum() or ch in {".", "-"} for ch in symbol):
            continue
        if symbol not in seen:
            seen.add(symbol)
            output.append(symbol)
        if len(output) >= 1000:
            break
    if not output:
        raise ValueError("At least one valid symbol is required")
    return output


def save_governed_universe(request: dict[str, Any]) -> dict[str, Any]:
    symbols = normalize_universe(request.get("symbols"))
    payload = {
        "governed_dislocation_universe_id": UNIVERSE_ID,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "source_name": str(request.get("source_name") or "GOVERNED_USER_SUPPLIED_UNIVERSE"),
        "as_of": str(request.get("as_of") or utc_now()),
        "strict_membership": True,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
        "updated_at": utc_now(),
    }
    record_object(UNIVERSE_ID, UNIVERSE_TYPE, SOURCE_CASE, payload)
    record_event(
        SOURCE_CASE,
        "GOVERNED_DISLOCATION_UNIVERSE_UPDATED",
        entity_id=UNIVERSE_ID,
        payload={"symbol_count": len(symbols), "trade_execution_permission": False},
    )
    return payload


def current_governed_universe() -> dict[str, Any] | None:
    return latest_object(UNIVERSE_TYPE, case_id=SOURCE_CASE)


def _research_query(institution: str) -> str:
    return f'"{institution}" (equity outlook OR sector outlook OR investment strategy OR market outlook OR research)'


def discover_public_institutional_research(limit_per_institution: int = 4) -> dict[str, Any]:
    limit_per_institution = max(1, min(int(limit_per_institution), 8))
    discoveries: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for row in SOURCE_REGISTRY:
        institution = _institution_name(row)
        if not institution:
            continue
        try:
            items = fetch_google_news_rss({"query": _research_query(institution), "limit": limit_per_institution})
        except Exception as exc:
            errors[institution] = f"{type(exc).__name__}: {exc}"
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            record_id = f"institutional_discovery_{uuid4().hex}"
            record = {
                "institutional_research_discovery_id": record_id,
                "institution": institution,
                "title": item.get("title"),
                "url": item.get("url"),
                "published_at": item.get("timestamp"),
                "discovery_source": item.get("source"),
                "source_type": "PUBLIC_DISCOVERY",
                "full_report_acquired": False,
                "authorized_access_required_for_restricted_content": True,
                "sentiment_eligible": False,
                "gap_resolution_eligible": False,
                "context_only": True,
                "trade_signal": False,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": utc_now(),
            }
            record_object(record_id, "institutional_research_discovery", SOURCE_CASE, record)
            discoveries.append(record)

    snapshot_id = f"institutional_discovery_snapshot_{uuid4().hex}"
    snapshot = {
        "institutional_discovery_snapshot_id": snapshot_id,
        "institution_count": len({_institution_name(x) for x in SOURCE_REGISTRY if _institution_name(x)}),
        "discovery_count": len(discoveries),
        "failed_institutions": errors,
        "discoveries": discoveries,
        "public_discovery_only": True,
        "private_bank_entitlement_bypass": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(snapshot_id, "institutional_discovery_snapshot", SOURCE_CASE, snapshot)
    record_event(
        SOURCE_CASE,
        "PUBLIC_INSTITUTIONAL_RESEARCH_DISCOVERY_COMPLETE",
        entity_id=snapshot_id,
        payload={"discovery_count": len(discoveries), "trade_execution_permission": False},
    )
    return snapshot


def ingest_authorized_research_inbox(inbox: Path | None = None, processed: Path | None = None) -> dict[str, Any]:
    inbox = inbox or Path(os.getenv("IIOS_RESEARCH_INBOX", str(DEFAULT_INBOX)))
    processed = processed or Path(os.getenv("IIOS_RESEARCH_PROCESSED", str(DEFAULT_PROCESSED)))
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    imported: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for path in sorted(inbox.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("research file must contain a JSON object")
            payload["access_tier"] = str(payload.get("access_tier") or "AUTHORIZED_USER_SUPPLIED")
            record = ingest_report(payload)
            imported.append({"file": path.name, "institutional_research_id": record.get("institutional_research_id")})
            destination = processed / path.name
            if destination.exists():
                destination = processed / f"{path.stem}_{uuid4().hex[:8]}{path.suffix}"
            shutil.move(str(path), str(destination))
        except Exception as exc:
            errors[path.name] = f"{type(exc).__name__}: {exc}"

    result = {
        "inbox": str(inbox),
        "processed": str(processed),
        "imported_count": len(imported),
        "error_count": len(errors),
        "imported": imported,
        "errors": errors,
        "full_proprietary_report_redistribution": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(f"authorized_research_inbox_run_{uuid4().hex}", "authorized_research_inbox_run", SOURCE_CASE, result)
    return result


def _fetch_json_url(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": GENERIC_USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Fed probability feed must return a JSON object")
    return payload


def read_fed_probability_source() -> dict[str, Any]:
    url = str(os.getenv("IIOS_FED_PROBABILITY_URL") or "").strip()
    file_path = Path(os.getenv("IIOS_FED_PROBABILITY_FILE", str(DEFAULT_FED_FILE)))

    if url:
        payload = _fetch_json_url(url)
        source_mode = "GOVERNED_JSON_URL"
        source_ref = url
    elif file_path.exists():
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Fed probability file must contain a JSON object")
        source_mode = "GOVERNED_LOCAL_FILE"
        source_ref = str(file_path)
    else:
        return {
            "status": "SOURCE_NOT_CONFIGURED",
            "expected_url_env": "IIOS_FED_PROBABILITY_URL",
            "expected_file": str(file_path),
            "probabilities_invented": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    probabilities = payload.get("probabilities")
    if not isinstance(probabilities, dict) or not probabilities:
        raise ValueError("Fed probability source missing probabilities object")

    request_payload: dict[str, Any] = {
        "probabilities": probabilities,
        "market_implied_source": str(payload.get("source_name") or payload.get("source") or source_mode),
        "probability_source_verified": bool(payload.get("source_verified", payload.get("verified", False))),
    }
    if payload.get("actual_decision_bps") is not None:
        request_payload["actual_decision_bps"] = payload.get("actual_decision_bps")

    snapshot = build_monetary_policy_snapshot(request_payload)
    return {
        "status": "CAPTURED",
        "source_mode": source_mode,
        "source_ref": source_ref,
        "source_verified": request_payload["probability_source_verified"],
        "snapshot": snapshot,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def source_acquisition_status() -> dict[str, Any]:
    return {
        "governed_dislocation_universe": current_governed_universe(),
        "institutional_discovery": latest_object("institutional_discovery_snapshot", case_id=SOURCE_CASE),
        "authorized_inbox_last_run": latest_object("authorized_research_inbox_run", case_id=SOURCE_CASE),
        "research_inbox": str(Path(os.getenv("IIOS_RESEARCH_INBOX", str(DEFAULT_INBOX)))),
        "fed_probability_url_configured": bool(os.getenv("IIOS_FED_PROBABILITY_URL")),
        "fed_probability_file": str(Path(os.getenv("IIOS_FED_PROBABILITY_FILE", str(DEFAULT_FED_FILE)))),
        "private_bank_entitlement_bypass": False,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/intelligence/source-acquisition/status")
def get_source_acquisition_status():
    return source_acquisition_status()


@router.post("/intelligence/source-acquisition/public-research/run")
def run_public_research(request: dict[str, Any] = Body(default={})):
    return discover_public_institutional_research(int(request.get("limit_per_institution") or 4))


@router.post("/intelligence/source-acquisition/authorized-inbox/run")
def run_authorized_inbox():
    return ingest_authorized_research_inbox()


@router.post("/intelligence/source-acquisition/fed-probability/run")
def run_fed_probability():
    try:
        return read_fed_probability_source()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")


@router.get("/intelligence/dislocation/universe")
def get_dislocation_universe():
    universe = current_governed_universe()
    return {
        "universe": universe,
        "strict_membership_active": bool(universe),
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/intelligence/dislocation/universe")
def set_dislocation_universe(request: dict[str, Any] = Body(...)):
    try:
        return save_governed_universe(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
