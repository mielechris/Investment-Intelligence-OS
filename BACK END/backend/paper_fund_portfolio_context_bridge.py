from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from factory_genericization import resolve_case_profile
from generic_coverage_v2 import COMPANY_PROFILES
from ledger import get_object, latest_object, record_event, record_object, utc_now
from paper_portfolio_core import build_portfolio_state


router = APIRouter()
POLICY_VERSION = "paper-fund-portfolio-context-v1"
SNAPSHOT_SOURCE = "GOVERNED_PAPER_PORTFOLIO"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _known_sector(value: Any) -> str:
    sector = str(value or "").strip()
    if not sector or sector == "GENERIC_PUBLIC_COMPANY":
        return ""
    return sector


def _sector_for_ticker(ticker: str) -> str:
    profile = COMPANY_PROFILES.get(str(ticker or "").upper()) or {}
    return _known_sector(profile.get("sector"))


def _position_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    nav = _safe_float(state.get("nav"))
    output: list[dict[str, Any]] = []
    for row in state.get("positions") or []:
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        market_value = _safe_float(row.get("market_value"))
        weight = (market_value / nav * 100.0) if nav > 0 else 0.0
        output.append(
            {
                "ticker": ticker,
                "weight_pct": round(weight, 4),
                "sector": _sector_for_ticker(ticker),
                "factors": [],
                "quantity": int(row.get("quantity") or 0),
                "market_value": round(market_value, 2),
                "average_cost": row.get("average_cost"),
                "mark_price": row.get("mark_price"),
                "mark_source": row.get("mark_source"),
            }
        )
    return output


def _overlap(
    candidate_ticker: str,
    candidate_sector: str,
    positions: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_ticker = str(candidate_ticker or "").upper()
    candidate_sector_norm = _known_sector(candidate_sector).lower()
    exact = 0.0
    sector = 0.0
    combined = 0.0
    overlapping: list[dict[str, Any]] = []

    for row in positions:
        weight = _safe_float(row.get("weight_pct"))
        same_ticker = bool(candidate_ticker and str(row.get("ticker") or "").upper() == candidate_ticker)
        row_sector = _known_sector(row.get("sector"))
        same_sector = bool(
            candidate_sector_norm
            and row_sector
            and row_sector.lower() == candidate_sector_norm
        )
        if same_ticker:
            exact += weight
        if same_sector:
            sector += weight
        if same_ticker or same_sector:
            combined += weight
            overlapping.append(
                {
                    "ticker": row.get("ticker"),
                    "weight_pct": round(weight, 4),
                    "same_ticker": same_ticker,
                    "same_sector": same_sector,
                    "shared_factors": [],
                }
            )

    combined = min(100.0, combined)
    level = "HIGH" if combined >= 50 else "MODERATE" if combined >= 25 else "LOW"
    return {
        "exact_ticker_weight_pct": round(exact, 4),
        "same_sector_weight_pct": round(sector, 4),
        "factor_overlap_weight_pct": 0.0,
        "combined_overlap_weight_pct": round(combined, 4),
        "concentration_level": level,
        "overlapping_positions": overlapping,
    }


def build_paper_fund_portfolio_context(case_id: str) -> dict[str, Any]:
    case = get_object(case_id)
    if not case or not str(case_id).startswith("case_"):
        raise ValueError("Unknown case_id")

    identity = resolve_case_profile(case_id)
    state = build_portfolio_state()
    positions = _position_rows(state)
    candidate_ticker = str(identity.get("ticker") or "").strip().upper()
    candidate_sector = _known_sector(identity.get("sector_profile"))
    overlap = _overlap(candidate_ticker, candidate_sector, positions)

    known_position_sectors = sum(1 for row in positions if _known_sector(row.get("sector")))
    if not positions:
        context_state = "CURRENT_CASH_ONLY"
        classification_status = "NOT_REQUIRED_NO_POSITIONS"
    elif candidate_sector and known_position_sectors == len(positions):
        context_state = "CURRENT_SECTOR_AWARE"
        classification_status = "SECTOR_CLASSIFICATION_COMPLETE"
    else:
        context_state = "CURRENT_EXACT_TICKER_ONLY"
        classification_status = "SECTOR_CLASSIFICATION_PARTIAL"

    snapshot_id = f"portfolio_snapshot_paper_fund_{case_id}"
    snapshot = {
        "portfolio_snapshot_id": snapshot_id,
        "policy_version": POLICY_VERSION,
        "case_id": case_id,
        "candidate_ticker": candidate_ticker or None,
        "candidate_sector": candidate_sector,
        "candidate_factors": [],
        "positions": positions,
        "position_count": len(positions),
        "weight_sum_pct": round(sum(_safe_float(row.get("weight_pct")) for row in positions), 4),
        "cash": state.get("cash"),
        "nav": state.get("nav"),
        "cash_weight_pct": (
            round((_safe_float(state.get("cash")) / _safe_float(state.get("nav"))) * 100.0, 4)
            if _safe_float(state.get("nav")) > 0
            else None
        ),
        "overlap": overlap,
        "context_state": context_state,
        "classification_status": classification_status,
        "known_position_sector_count": known_position_sectors,
        "source": SNAPSHOT_SOURCE,
        "paper_portfolio_account_id": state.get("paper_portfolio_account_id"),
        "accounting_scope": state.get("accounting_scope"),
        "as_of": state.get("generated_at") or utc_now(),
        "created_at": utc_now(),
        "first_party_governed_source": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }

    record_object(
        snapshot_id,
        "portfolio_snapshot",
        case_id,
        snapshot,
        parent_id=str(state.get("paper_portfolio_account_id") or "paper_portfolio_default"),
        topic=case.get("topic"),
    )
    record_event(
        case_id,
        "PAPER_FUND_PORTFOLIO_CONTEXT_SYNCED",
        entity_id=snapshot_id,
        payload={
            "nav": snapshot.get("nav"),
            "cash": snapshot.get("cash"),
            "position_count": snapshot.get("position_count"),
            "exact_ticker_weight_pct": overlap.get("exact_ticker_weight_pct"),
            "same_sector_weight_pct": overlap.get("same_sector_weight_pct"),
            "context_state": context_state,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return snapshot


def install_paper_fund_portfolio_context_bridge(monitoring_module: Any) -> None:
    if getattr(monitoring_module, "_paper_fund_portfolio_context_installed", False):
        return
    prior_refresh = monitoring_module.refresh_profile

    def refresh_profile_with_paper_fund_context(profile: dict[str, Any]):
        result = prior_refresh(profile)
        case_id = str(profile.get("case_id") or "")
        try:
            result["paper_fund_portfolio_context"] = build_paper_fund_portfolio_context(case_id)
        except Exception as exc:
            result["paper_fund_portfolio_context"] = {
                "state": "ERROR_FAIL_CLOSED",
                "error": f"{type(exc).__name__}: {exc}",
                "paper_mode": True,
                "trade_execution_permission": False,
                "live_execution": False,
            }
        return result

    monitoring_module.refresh_profile = refresh_profile_with_paper_fund_context
    monitoring_module._paper_fund_portfolio_context_installed = True


@router.get("/portfolio-context/{case_id}/paper-fund")
def paper_fund_context_status(case_id: str):
    if not get_object(case_id):
        raise HTTPException(status_code=404, detail="Unknown case_id")
    snapshot = latest_object("portfolio_snapshot", case_id=case_id) or {}
    if snapshot.get("source") != SNAPSHOT_SOURCE:
        snapshot = {}
    return {
        "case_id": case_id,
        "snapshot": snapshot or None,
        "source": SNAPSHOT_SOURCE,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.post("/portfolio-context/{case_id}/sync-paper-fund")
def sync_paper_fund_context(case_id: str):
    try:
        snapshot = build_paper_fund_portfolio_context(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "case_id": case_id,
        "snapshot": snapshot,
        "paper_mode": True,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
