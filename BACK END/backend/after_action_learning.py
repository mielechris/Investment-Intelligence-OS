"""IIOS shadow-only after-action learning.

This module evaluates the quality of past decisions after outcome data becomes
available. It cannot submit orders, change thresholds, or promote a challenger.
All outputs are recommendations/measurements for human-governed review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class OutcomeWindow:
    horizon: str
    decision_price: float
    end_price: float
    max_favorable_price: float
    max_adverse_price: float

    def metrics(self, direction: str = "LONG") -> dict:
        if self.decision_price <= 0:
            raise ValueError("decision_price must be positive")
        direction = direction.upper()
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        sign = 1.0 if direction == "LONG" else -1.0
        realized = sign * ((self.end_price / self.decision_price) - 1.0)
        favorable = sign * ((self.max_favorable_price / self.decision_price) - 1.0)
        adverse = sign * ((self.max_adverse_price / self.decision_price) - 1.0)
        mfe = max(0.0, favorable)
        mae = min(0.0, adverse)
        return {
            "horizon": self.horizon,
            "return": realized,
            "mfe": mfe,
            "mae": mae,
        }


@dataclass(frozen=True)
class ThesisExpectations:
    direction: str = "LONG"
    expected_move_pct: Optional[float] = None
    max_tolerated_drawdown_pct: Optional[float] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None


@dataclass(frozen=True)
class AfterActionAssessment:
    case_id: str
    ticker: str
    original_decision: str
    original_score: Optional[float]
    market_regime: Optional[str]
    horizon: str
    return_pct: float
    mfe_pct: float
    mae_pct: float
    thesis_supported: Optional[bool]
    risk_respected: Optional[bool]
    veto_value_pct: Optional[float]
    opportunity_cost_pct: Optional[float]
    quality_notes: Sequence[str] = field(default_factory=tuple)
    shadow_only: bool = True
    portfolio_effect: str = "NONE"
    automatic_rule_change: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def assess_decision(
    *,
    case_id: str,
    ticker: str,
    original_decision: str,
    original_score: Optional[float],
    market_regime: Optional[str],
    outcome: OutcomeWindow,
    thesis: ThesisExpectations,
) -> AfterActionAssessment:
    """Evaluate a prior decision without hindsight-forcing a binary label.

    NO_TRADE/VETO outcomes separately expose avoided drawdown and opportunity
    cost. A positive later return does not automatically make the original
    decision bad; thesis and risk expectations are considered explicitly.
    """
    metrics = outcome.metrics(thesis.direction)
    ret = metrics["return"]
    mfe = metrics["mfe"]
    mae = metrics["mae"]
    decision = original_decision.upper().strip()

    thesis_supported: Optional[bool] = None
    if thesis.expected_move_pct is not None:
        threshold = thesis.expected_move_pct / 100.0
        thesis_supported = mfe >= threshold
    elif thesis.target_price is not None:
        if thesis.direction.upper() == "LONG":
            thesis_supported = outcome.max_favorable_price >= thesis.target_price
        else:
            thesis_supported = outcome.max_favorable_price <= thesis.target_price

    risk_respected: Optional[bool] = None
    if thesis.max_tolerated_drawdown_pct is not None:
        limit = abs(thesis.max_tolerated_drawdown_pct) / 100.0
        risk_respected = abs(mae) <= limit
    elif thesis.stop_price is not None:
        if thesis.direction.upper() == "LONG":
            risk_respected = outcome.max_adverse_price > thesis.stop_price
        else:
            risk_respected = outcome.max_adverse_price < thesis.stop_price

    veto_value: Optional[float] = None
    opportunity_cost: Optional[float] = None
    notes: List[str] = []

    if decision in {"NO_TRADE", "VETO", "REJECTED"}:
        veto_value = abs(mae) if mae < 0 else 0.0
        opportunity_cost = max(0.0, mfe)
        notes.append("rejected-case outcome measured in shadow only")
        if veto_value and opportunity_cost:
            notes.append("decision avoided drawdown but also passed on upside")
        elif veto_value:
            notes.append("decision avoided observed adverse excursion")
        elif opportunity_cost:
            notes.append("decision passed on observed favorable excursion")
    else:
        notes.append("approved-case outcome evaluated against original thesis and risk")

    if thesis_supported is False:
        notes.append("original expected move was not observed within this horizon")
    if risk_respected is False:
        notes.append("observed adverse excursion exceeded original risk tolerance")

    return AfterActionAssessment(
        case_id=case_id,
        ticker=ticker.upper(),
        original_decision=decision,
        original_score=original_score,
        market_regime=market_regime,
        horizon=outcome.horizon,
        return_pct=ret * 100.0,
        mfe_pct=mfe * 100.0,
        mae_pct=mae * 100.0,
        thesis_supported=thesis_supported,
        risk_respected=risk_respected,
        veto_value_pct=None if veto_value is None else veto_value * 100.0,
        opportunity_cost_pct=None if opportunity_cost is None else opportunity_cost * 100.0,
        quality_notes=tuple(notes),
    )


def summarize_by_regime(assessments: Iterable[AfterActionAssessment]) -> Dict[str, dict]:
    buckets: Dict[str, List[AfterActionAssessment]] = {}
    for item in assessments:
        buckets.setdefault(item.market_regime or "UNKNOWN", []).append(item)

    result: Dict[str, dict] = {}
    for regime, items in buckets.items():
        veto_values = [x.veto_value_pct for x in items if x.veto_value_pct is not None]
        opportunity_costs = [x.opportunity_cost_pct for x in items if x.opportunity_cost_pct is not None]
        result[regime] = {
            "cases": len(items),
            "avg_return_pct": sum(x.return_pct for x in items) / len(items),
            "avg_mae_pct": sum(x.mae_pct for x in items) / len(items),
            "avg_mfe_pct": sum(x.mfe_pct for x in items) / len(items),
            "avg_veto_value_pct": (sum(veto_values) / len(veto_values)) if veto_values else None,
            "avg_veto_opportunity_cost_pct": (
                sum(opportunity_costs) / len(opportunity_costs)
            ) if opportunity_costs else None,
            "shadow_only": True,
        }
    return result
