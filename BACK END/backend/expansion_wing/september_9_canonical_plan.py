"""Single canonical contract for the corrected September 9 evidence plan."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .tuesday_whole_factory import PILOT_BY_PRODUCT

PLAN_SCHEMA = "iios-september-9-operational-plan-v2"
PLAN_CLASSIFICATION = "SEPTEMBER_9_MARKET_OPEN_50"
SESSION_DATE = "2026-09-09"
PROVIDER = "FINANCIAL_DATASETS"
PROVIDER_CONTRACT = "fd-stage-a-standard-v1"
OBSOLETE_READINESS_IDENTITY = "d08262228104ee464d602688aae6e1c97e67db10e640233deff87a1231e63c23"
OBSOLETE_EXECUTOR_IDENTITY = "c40b4c241d114df4d95069e55e7c68a4fbc8e1c899c5faa6aa8e3767b97a626a"
PATHS = {"MARKET_SNAPSHOT":"/prices/snapshot", "HISTORICAL_OHLCV":"/prices", "COMPANY_FACTS":"/company/facts"}
LEGACY_WINDOWS = {"OPENING":("06:30","07:00"),"BASELINE":("06:30","09:30"),
    "INTRADAY":("09:30","12:55"),"CLOSING":("12:55","13:05")}


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _request_identity(row: dict[str, Any]) -> str:
    material = {key: row[key] for key in (
        "provider", "provider_contract", "plan", "session_date", "ticker", "observation_type", "variant",
        "window", "earliest", "latest", "endpoint", "path", "start_date", "end_date", "cost", "retry")}
    return "market-evidence-" + _hash({"schema":"iios-material-request-identity-v2", "request":material})


def _row(*, room: str, ticker: str, observation_type: str, variant: str, earliest: str, latest: str,
         endpoint: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    row = {"provider":PROVIDER, "provider_contract":PROVIDER_CONTRACT, "plan":PLAN_CLASSIFICATION, "session_date":SESSION_DATE,
        "ticker":ticker, "product_room":room, "observation_type":observation_type, "variant":variant,
        "window":"BASELINE" if observation_type in {"POINT_IN_TIME_OHLCV","PRIOR_SESSION_BASELINE","APPLICABLE_FACTS"} else observation_type,
        "earliest":earliest, "latest":latest, "endpoint":endpoint, "path":PATHS[endpoint],
        "start_date":start_date, "end_date":end_date, "cost":1, "retry":False}
    return {"identity":_request_identity(row), **row}


def corrected_september_9_plan() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for room, (ticker, _description) in PILOT_BY_PRODUCT.items():
        rows.append(_row(room=room,ticker=ticker,observation_type="OPENING",variant="STANDARD",earliest="06:30",latest="07:00",endpoint="MARKET_SNAPSHOT"))
        rows.append(_row(room=room,ticker=ticker,observation_type="POINT_IN_TIME_OHLCV",variant="STANDARD",earliest="06:30",latest="09:30",endpoint="HISTORICAL_OHLCV",start_date="2026-09-08",end_date="2026-09-09"))
        if ticker == "MU":
            rows.append(_row(room=room,ticker=ticker,observation_type="APPLICABLE_FACTS",variant="STANDARD",earliest="06:30",latest="09:30",endpoint="COMPANY_FACTS"))
        else:
            rows.append(_row(room=room,ticker=ticker,observation_type="PRIOR_SESSION_BASELINE",variant="FUND_BASELINE",earliest="06:30",latest="09:30",endpoint="HISTORICAL_OHLCV",start_date="2026-09-08",end_date="2026-09-08"))
        rows.append(_row(room=room,ticker=ticker,observation_type="INTRADAY",variant="STANDARD",earliest="09:30",latest="12:55",endpoint="MARKET_SNAPSHOT"))
        rows.append(_row(room=room,ticker=ticker,observation_type="CLOSING",variant="STANDARD",earliest="12:55",latest="13:05",endpoint="MARKET_SNAPSHOT"))
    return tuple(rows)


def obsolete_c40_plan() -> tuple[dict[str, Any], ...]:
    """Reconstruct the incident plan solely to authenticate its quarantine."""
    tickers=tuple(value[0] for value in PILOT_BY_PRODUCT.values()); rows=[]
    def legacy(window:str,endpoint:str,ticker:str,variant:str="STANDARD"):
        earliest,latest=LEGACY_WINDOWS[window]
        seed=f"{SESSION_DATE}|{PLAN_CLASSIFICATION}|{window}|{endpoint}:{variant}|{ticker}|fd-operational-v1"
        return {"identity":"market-evidence-"+hashlib.sha256(seed.encode()).hexdigest(),"plan":PLAN_CLASSIFICATION,
            "session_date":SESSION_DATE,"window":window,"endpoint":endpoint,"path":PATHS[endpoint],"ticker":ticker,
            "earliest":earliest,"latest":latest,"cost":1,"retry":False,"variant":variant}
    for ticker in tickers:
        rows.extend((legacy("OPENING","MARKET_SNAPSHOT",ticker),legacy("BASELINE","HISTORICAL_OHLCV",ticker),
            legacy("INTRADAY","MARKET_SNAPSHOT",ticker),legacy("CLOSING","MARKET_SNAPSHOT",ticker)))
    rows.append(legacy("BASELINE","COMPANY_FACTS","MU"))
    rows.extend(legacy("BASELINE","HISTORICAL_OHLCV",ticker,"FUND_BASELINE") for ticker in tickers if ticker!="MU")
    result=tuple(rows)
    raw=json.dumps(result,sort_keys=True,separators=(",",":")).encode()
    if hashlib.sha256(raw).hexdigest()!=OBSOLETE_EXECUTOR_IDENTITY: raise ValueError("OBSOLETE_PLAN_RECONSTRUCTION_FAILED")
    return result


def canonical_plan_document(rows: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any]:
    selected = corrected_september_9_plan() if rows is None else rows
    return {"schema":PLAN_SCHEMA, "classification":PLAN_CLASSIFICATION, "session_date":SESSION_DATE,
        "maximum_requests":50, "maximum_credits":50, "automatic_retries":0, "rows":list(selected)}


def canonical_plan_bytes(rows: tuple[dict[str, Any], ...] | None = None) -> bytes:
    return _canonical(canonical_plan_document(rows))


def canonical_plan_identity(rows: tuple[dict[str, Any], ...] | None = None) -> str:
    return hashlib.sha256(canonical_plan_bytes(rows)).hexdigest()


def validate_canonical_plan(rows: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    expected = corrected_september_9_plan()
    if rows != expected or len(rows) != 50 or len({row["identity"] for row in rows}) != 50:
        raise ValueError("SEPTEMBER_9_CANONICAL_PLAN_INVALID")
    identity = canonical_plan_identity(rows)
    if identity in {OBSOLETE_READINESS_IDENTITY, OBSOLETE_EXECUTOR_IDENTITY}:
        raise ValueError("SEPTEMBER_9_OBSOLETE_PLAN_IDENTITY")
    return rows


def mutated_identity(index: int, field: str, value: Any) -> str:
    rows = [deepcopy(row) for row in corrected_september_9_plan()]
    rows[index][field] = value
    return canonical_plan_identity(tuple(rows))
