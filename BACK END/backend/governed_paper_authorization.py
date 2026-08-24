from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from ledger import (
    consume_paper_authorization,
    get_object,
    paper_authorization_consumed,
    record_event,
    record_object,
    utc_now,
)


AUTHORIZATION_VERSION = (
    "GOVERNED_PAPER_AUTHORIZATION_V1"
)


def _canonical_binding(
    *,
    case_id: str,
    qualification: dict[str, Any],
    thesis_status: dict[str, Any],
    capital_gate: dict[str, Any],
    sizing: dict[str, Any],
) -> dict[str, Any]:
    """
    The authorization is cryptographically bound to the exact
    governed state that earned it.
    """

    return {
        "case_id": str(case_id),

        "research_stage":
            qualification.get("stage"),
        "qualified_buy_candidate":
            qualification.get(
                "qualified_buy_candidate"
            ),

        "thesis_status":
            thesis_status.get("status"),
        "thesis_invalidated":
            thesis_status.get(
                "thesis_invalidated"
            ),
        "thesis_breached_rules":
            sorted(
                str(x)
                for x in (
                    thesis_status.get(
                        "breached_rules"
                    )
                    or []
                )
            ),

        "capital_decision":
            capital_gate.get("decision"),
        "capital_entry_price":
            capital_gate.get(
                "current_price"
            ),
        "capital_reward_risk":
            capital_gate.get(
                "reward_risk"
            ),

        "sizing_decision":
            sizing.get("decision"),
        "proposed_shares":
            sizing.get("proposed_shares"),
        "proposed_notional":
            sizing.get(
                "proposed_notional"
            ),
        "invalidation_price":
            sizing.get(
                "invalidation_price"
            ),
        "invalidation_basis":
            sizing.get(
                "invalidation_basis"
            ),
        "portfolio_nav":
            sizing.get("portfolio_nav"),
        "portfolio_overlap_pct":
            sizing.get(
                "combined_overlap_weight_pct"
            ),
    }


def _fingerprint(
    binding: dict[str, Any],
) -> str:
    encoded = json.dumps(
        binding,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def create_paper_authorization(
    *,
    case_id: str,
    qualification: dict[str, Any],
    thesis_status: dict[str, Any],
    capital_gate: dict[str, Any],
    sizing: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a one-time paper authorization token.

    IMPORTANT:
    This token is NOT yet accepted by Paper Execution.
    """

    checks = {
        "qualified_buy_candidate": (
            qualification.get(
                "qualified_buy_candidate"
            )
            is True
        ),

        "thesis_active": (
            thesis_status.get("status")
            in {
                "ACTIVE_CLEAR",
                "ACTIVE_WITH_WATCHES",
            }
            and thesis_status.get(
                "thesis_invalidated"
            )
            is False
            and not (
                thesis_status.get(
                    "breached_rules"
                )
                or []
            )
        ),

        "thesis_mapper_deterministic": (
            (
                thesis_status.get(
                    "governance"
                )
                or {}
            ).get(
                "deterministic_mapper"
            )
            is True
        ),

        "capital_gate_approved": (
            capital_gate.get("decision")
            == "APPROVED"
        ),

        "capital_hard_fails_clear": (
            not (
                capital_gate.get(
                    "failed_hard_checks"
                )
                or []
            )
        ),

        "capital_reward_risk_passed": (
            (
                capital_gate.get(
                    "checks"
                )
                or {}
            ).get(
                "reward_risk_passed"
            )
            is True
        ),

        "size_ready": (
            sizing.get("decision")
            == "SIZE_READY"
        ),

        "positive_proposed_shares": (
            int(
                sizing.get(
                    "proposed_shares"
                )
                or 0
            )
            > 0
        ),

        "positive_proposed_notional": (
            float(
                sizing.get(
                    "proposed_notional"
                )
                or 0.0
            )
            > 0
        ),

        "sizing_execution_still_locked": (
            sizing.get(
                "paper_order_permission"
            )
            is False
            and sizing.get(
                "trade_execution_permission"
            )
            is False
        ),
    }

    failed = [
        key
        for key, passed in checks.items()
        if not passed
    ]

    if failed:
        return {
            "decision":
                "AUTHORIZATION_DENIED",
            "failed_checks": failed,
            "checks": checks,
            "authorization_id": None,
            "paper_execution_ready":
                False,
            "trade_execution_permission":
                False,
        }

    binding = _canonical_binding(
        case_id=case_id,
        qualification=qualification,
        thesis_status=thesis_status,
        capital_gate=capital_gate,
        sizing=sizing,
    )

    fingerprint = _fingerprint(
        binding
    )

    authorization_id = (
        f"paper_auth_{uuid4().hex}"
    )

    authorization = {
        "paper_authorization_id":
            authorization_id,
        "authorization_version":
            AUTHORIZATION_VERSION,
        "case_id":
            case_id,

        "decision":
            "AUTHORIZED_FOR_PAPER_HANDOFF",

        "binding":
            binding,
        "binding_sha256":
            fingerprint,

        "checks":
            checks,
        "failed_checks":
            [],

        # This is the amount that a future bridge MAY pass
        # to Paper Execution after all token checks pass.
        "authorized_shares":
            int(
                sizing.get(
                    "proposed_shares"
                )
            ),
        "authorized_notional":
            float(
                sizing.get(
                    "proposed_notional"
                )
            ),

        "entry_price":
            float(
                capital_gate.get(
                    "current_price"
                )
            ),
        "invalidation_price":
            float(
                sizing.get(
                    "invalidation_price"
                )
            ),
        "invalidation_basis":
            str(
                sizing.get(
                    "invalidation_basis"
                )
            ),

        "single_use":
            True,

        # Still disconnected from current paper execution.
        "paper_execution_ready":
            False,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
        "live_execution":
            False,

        "created_at":
            utc_now(),
    }

    record_object(
        authorization_id,
        "paper_authorization",
        case_id,
        authorization,
    )

    record_event(
        case_id,
        "PAPER_AUTHORIZATION_CREATED",
        entity_id=authorization_id,
        payload={
            "authorization_version":
                AUTHORIZATION_VERSION,
            "binding_sha256":
                fingerprint,
            "authorized_shares":
                authorization[
                    "authorized_shares"
                ],
            "authorized_notional":
                authorization[
                    "authorized_notional"
                ],
            "paper_execution_ready":
                False,
            "trade_execution_permission":
                False,
        },
    )

    return authorization


def verify_paper_authorization(
    *,
    authorization_id: str,
    current_binding: dict[str, Any],
) -> dict[str, Any]:
    authorization = get_object(
        authorization_id
    )

    if not authorization:
        return {
            "valid": False,
            "reason":
                "AUTHORIZATION_NOT_FOUND",
        }

    if not str(
        authorization_id
    ).startswith("paper_auth_"):
        return {
            "valid": False,
            "reason":
                "WRONG_AUTHORIZATION_TYPE",
        }

    consumed = (
        paper_authorization_consumed(
            authorization_id
        )
    )

    if consumed is None:
        return {
            "valid": False,
            "reason":
                "AUTHORIZATION_STATE_MISSING",
        }

    if consumed:
        return {
            "valid": False,
            "reason":
                "AUTHORIZATION_ALREADY_CONSUMED",
        }

    expected = str(
        authorization.get(
            "binding_sha256"
        )
        or ""
    )

    actual = _fingerprint(
        current_binding
    )

    if expected != actual:
        return {
            "valid": False,
            "reason":
                "AUTHORIZATION_BINDING_MISMATCH",
            "expected_sha256":
                expected,
            "actual_sha256":
                actual,
        }

    return {
        "valid": True,
        "reason": None,
        "authorization_id":
            authorization_id,
        "binding_sha256":
            actual,
        "authorized_shares":
            authorization.get(
                "authorized_shares"
            ),
        "authorized_notional":
            authorization.get(
                "authorized_notional"
            ),
        "paper_execution_ready":
            False,
        "trade_execution_permission":
            False,
    }


def consume_verified_paper_authorization(
    *,
    authorization_id: str,
    current_binding: dict[str, Any],
) -> dict[str, Any]:
    verification = (
        verify_paper_authorization(
            authorization_id=
                authorization_id,
            current_binding=
                current_binding,
        )
    )

    if not verification.get("valid"):
        return {
            **verification,
            "consumed": False,
        }

    consumed = consume_paper_authorization(
        authorization_id
    )

    if not consumed:
        return {
            "valid": False,
            "reason":
                "AUTHORIZATION_CONSUME_FAILED",
            "consumed": False,
        }

    return {
        **verification,
        "consumed": True,

        # Even successful consumption does NOT execute.
        "paper_execution_ready":
            False,
        "paper_order_permission":
            False,
        "trade_execution_permission":
            False,
    }
