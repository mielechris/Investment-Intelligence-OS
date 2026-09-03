from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class PointInTimeObservation:
    timestamp: str
    features_known_then: dict[str, float]
    future_return: float
    regime: str
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    feature_observed_at: dict[str, str] | None = None


def walk_forward_test(observations: list[PointInTimeObservation], rule: Callable[[dict[str, float]], bool],
                      *, minimum_train: int = 2) -> dict[str, Any]:
    ordered = sorted(observations, key=lambda row: row.timestamp)
    if len(ordered) <= minimum_train:
        return {"status": "INCOMPLETE", "reason": "INSUFFICIENT_WALK_FORWARD_SAMPLE"}
    outcomes: list[float] = []
    equity = peak = 0.0
    max_drawdown = 0.0
    regimes: set[str] = set()
    for index in range(minimum_train, len(ordered)):
        test = ordered[index]
        if test.feature_observed_at:
            try:
                as_of = datetime.fromisoformat(test.timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)
                feature_times = [datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
                                 for value in test.feature_observed_at.values()]
            except (TypeError, ValueError):
                return {"status": "REJECTED", "reason": "MALFORMED_POINT_IN_TIME_TIMESTAMP", "point_in_time": False}
            if any(value > as_of for value in feature_times):
                return {"status": "REJECTED", "reason": "LOOK_AHEAD_FEATURE_DETECTED", "point_in_time": False}
        regimes.add(test.regime)
        if not rule(dict(test.features_known_then)):
            continue
        outcome = test.future_return - test.spread_cost - test.slippage_cost
        outcomes.append(outcome)
        equity += outcome
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {"status": "COMPLETE", "trades": len(outcomes), "net_return": round(sum(outcomes), 6),
            "max_drawdown": round(max_drawdown, 6), "regimes": sorted(regimes),
            "point_in_time": True, "walk_forward": True, "transaction_costs_included": True,
            "failures_included": any(value <= 0 for value in outcomes), "forward_paper_validation_required": True}
