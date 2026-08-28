#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "batch10c-portfolio-intelligence-v1"


def _float(value: Any) -> float | None:
    try: return float(value)
    except (TypeError, ValueError): return None


def _int(value: Any) -> int:
    try: return int(value or 0)
    except (TypeError, ValueError): return 0


def build_portfolio(*, telemetry: dict[str, Any], generated_at: datetime | None = None) -> dict[str, Any]:
    fund = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
    positions = [row for row in fund.get("positions") or [] if isinstance(row, dict)]
    nav = _float(fund.get("nav")) or 0.0
    cash = _float(fund.get("cash")) or 0.0
    gross_long = 0.0
    gross_short = 0.0
    rows: list[dict[str, Any]] = []
    for position in positions:
        value = abs(_float(position.get("market_value")) or 0.0)
        direction = str(position.get("direction") or "LONG").upper()
        if direction == "SHORT": gross_short += value
        else: gross_long += value
        weight = (value / nav) * 100.0 if nav > 0 else None
        rows.append({
            "ticker": position.get("ticker"), "direction": direction,
            "market_value": _float(position.get("market_value")),
            "unrealized_pnl": _float(position.get("unrealized_pnl")),
            "unrealized_return_pct": _float(position.get("unrealized_return_pct")),
            "weight_pct": round(weight, 2) if weight is not None else None,
        })
    rows.sort(key=lambda row: abs(float(row.get("weight_pct") or 0.0)), reverse=True)
    top1 = rows[0].get("weight_pct") if rows else None
    top3 = round(sum(float(row.get("weight_pct") or 0.0) for row in rows[:3]), 2) if rows else None
    invested = gross_long + gross_short
    cash_pct = round((cash / nav) * 100.0, 2) if nav > 0 else None
    status = "CASH_ONLY_WARM_UP" if not rows else "PAPER_PORTFOLIO_INTELLIGENCE_ACTIVE"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": status,
        "nav": nav,
        "cash": cash,
        "cash_pct": cash_pct,
        "position_count": len(rows),
        "gross_long_exposure": round(gross_long, 2),
        "gross_short_exposure": round(gross_short, 2),
        "gross_exposure": round(invested, 2),
        "gross_exposure_pct": round((invested / nav) * 100.0, 2) if nav > 0 else None,
        "net_exposure": round(gross_long - gross_short, 2),
        "top_position_weight_pct": top1,
        "top_three_weight_pct": top3,
        "max_drawdown_pct": _float(fund.get("max_drawdown_pct")),
        "current_drawdown_pct": _float(fund.get("current_drawdown_pct")),
        "cumulative_return_pct": _float(fund.get("cumulative_return_pct")),
        "positions": rows,
        "measurement_gaps": [
            "sector and industry exposure are unavailable until classifications are persisted with positions",
            "factor beta and correlation require a governed historical return series",
            "liquidity-at-risk requires position-level market-liquidity measurements",
            "regime-conditioned portfolio behavior requires mature 9T-tagged outcomes",
        ],
        "advisory_flags": (["NO_PAPER_POSITIONS_TO_ANALYZE"] if not rows else []) + (["TOP_POSITION_CONCENTRATION_REVIEW"] if isinstance(top1, (int, float)) and top1 > 25 else []),
        "safety": {
            "paper_portfolio_only": True,
            "advisory_only": True,
            "auto_rebalance": False,
            "position_change_authority": False,
            "risk_rule_change_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    }
