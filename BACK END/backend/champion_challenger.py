"""Human-governed Champion vs Challenger evaluation for IIOS.

Challengers are shadow configurations only. This module compares evidence and
may recommend a review; it has no authority to mutate production configuration,
Risk rules, paper execution thresholds, broker state, or live-capital settings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class EvaluationMetrics:
    observations: int
    expectancy_pct: float
    max_drawdown_pct: float
    false_positive_rate: float
    missed_opportunity_rate: float
    calibration_error: float


@dataclass(frozen=True)
class ChallengerReview:
    champion_version: str
    challenger_version: str
    sufficient_evidence: bool
    recommended_for_human_review: bool
    reasons: tuple[str, ...]
    challenger_shadow_only: bool = True
    automatic_promotion: bool = False
    automatic_threshold_mutation: bool = False
    broker_connected: bool = False
    live_execution: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def compare(
    champion_version: str,
    challenger_version: str,
    champion: EvaluationMetrics,
    challenger: EvaluationMetrics,
    *,
    minimum_observations: int = 200,
    max_allowed_drawdown_increase_pct_points: float = 0.0,
) -> ChallengerReview:
    """Recommend human review only when a shadow challenger clears strict gates."""
    reasons: list[str] = []
    sufficient = (
        champion.observations >= minimum_observations
        and challenger.observations >= minimum_observations
    )
    if not sufficient:
        reasons.append(
            f"insufficient observations; require >= {minimum_observations} for both configurations"
        )

    expectancy_better = challenger.expectancy_pct > champion.expectancy_pct
    drawdown_ok = (
        challenger.max_drawdown_pct
        <= champion.max_drawdown_pct + max_allowed_drawdown_increase_pct_points
    )
    false_positive_better = (
        challenger.false_positive_rate <= champion.false_positive_rate
    )
    missed_opportunity_better = (
        challenger.missed_opportunity_rate <= champion.missed_opportunity_rate
    )
    calibration_better = challenger.calibration_error <= champion.calibration_error

    if expectancy_better:
        reasons.append("challenger expectancy improved")
    else:
        reasons.append("challenger expectancy did not improve")
    if drawdown_ok:
        reasons.append("challenger drawdown stayed within governance limit")
    else:
        reasons.append("challenger drawdown exceeded governance limit")
    if false_positive_better:
        reasons.append("challenger false-positive rate did not worsen")
    else:
        reasons.append("challenger false-positive rate worsened")
    if missed_opportunity_better:
        reasons.append("challenger missed-opportunity rate did not worsen")
    else:
        reasons.append("challenger missed-opportunity rate worsened")
    if calibration_better:
        reasons.append("challenger calibration did not worsen")
    else:
        reasons.append("challenger calibration worsened")

    recommend = all((
        sufficient,
        expectancy_better,
        drawdown_ok,
        false_positive_better,
        missed_opportunity_better,
        calibration_better,
    ))

    if recommend:
        reasons.append("eligible for HUMAN REVIEW only; no automatic promotion")

    return ChallengerReview(
        champion_version=champion_version,
        challenger_version=challenger_version,
        sufficient_evidence=sufficient,
        recommended_for_human_review=recommend,
        reasons=tuple(reasons),
    )
