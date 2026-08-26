from __future__ import annotations

from typing import Any
from uuid import uuid4

from governed_paper_authorization import (
    _canonical_binding,
    _capital_reward_risk_passed,
    consume_verified_paper_authorization,
    verify_paper_authorization,
)
from ledger import (
    get_object,
    record_event,
    record_object,
    utc_now,
)


def _blocked(
    *,
    case_id: str,
    reason: str,
    authorization_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "case_id":
            case_id,

        "paper_authorization_id":
            authorization_id,

        "status":
            "BLOCKED",

        "execution":
            "NOT_SUBMITTED",

        "reason":
            reason,

        "shares":
            0,

        "notional":
            0.0,

        **extra,

        "paper_mode":
            True,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }


def create_governed_paper_order(
    *,
    case_id: str,
    authorization_id: str,
    qualification: dict[str, Any],
    thesis_status: dict[str, Any],
    capital_gate: dict[str, Any],
    sizing: dict[str, Any],
) -> dict[str, Any]:

    if not str(
        authorization_id or ""
    ).startswith("paper_auth_"):
        return _blocked(
            case_id=case_id,
            reason=
                "INVALID_AUTHORIZATION_TYPE",
            authorization_id=
                authorization_id,
        )

    authorization = get_object(
        authorization_id
    )

    if not authorization:
        return _blocked(
            case_id=case_id,
            reason=
                "AUTHORIZATION_NOT_FOUND",
            authorization_id=
                authorization_id,
        )

    if (
        str(
            authorization.get(
                "case_id"
            )
            or ""
        )
        != str(case_id)
    ):
        return _blocked(
            case_id=case_id,
            reason=
                "CASE_BINDING_MISMATCH",
            authorization_id=
                authorization_id,
        )

    current_binding = (
        _canonical_binding(
            case_id=case_id,
            qualification=
                qualification,
            thesis_status=
                thesis_status,
            capital_gate=
                capital_gate,
            sizing=sizing,
        )
    )

    verification = (
        verify_paper_authorization(
            authorization_id=
                authorization_id,

            current_binding=
                current_binding,
        )
    )

    if not verification.get("valid"):
        return _blocked(
            case_id=case_id,
            reason=str(
                verification.get(
                    "reason"
                )
                or "AUTHORIZATION_INVALID"
            ),
            authorization_id=
                authorization_id,
        )

    hard_checks = {
        "qualified_candidate_current": (
            qualification.get(
                "qualified_buy_candidate"
            )
            is True
        ),

        "thesis_currently_valid": (
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

        "capital_still_approved": (
            capital_gate.get("decision")
            == "APPROVED"
        ),

        "capital_hard_checks_clear": (
            not (
                capital_gate.get(
                    "failed_hard_checks"
                )
                or []
            )
        ),

        "reward_risk_still_passed":
            _capital_reward_risk_passed(
                capital_gate
            ),

        "size_still_ready": (
            sizing.get("decision")
            == "SIZE_READY"
        ),

        "shares_positive": (
            int(
                sizing.get(
                    "proposed_shares"
                )
                or 0
            )
            > 0
        ),

        "notional_positive": (
            float(
                sizing.get(
                    "proposed_notional"
                )
                or 0.0
            )
            > 0
        ),
    }

    failed = [
        key
        for key, passed
        in hard_checks.items()
        if not passed
    ]

    if failed:
        return _blocked(
            case_id=case_id,
            reason=
                "CURRENT_STATE_NOT_EXECUTABLE",
            authorization_id=
                authorization_id,
            failed_checks=failed,
            checks=hard_checks,
        )

    authorized_shares = int(
        authorization.get(
            "authorized_shares"
        )
        or 0
    )

    current_shares = int(
        sizing.get(
            "proposed_shares"
        )
        or 0
    )

    if (
        authorized_shares
        != current_shares
    ):
        return _blocked(
            case_id=case_id,
            reason=
                "AUTHORIZED_SIZE_MISMATCH",
            authorization_id=
                authorization_id,

            authorized_shares=
                authorized_shares,

            current_shares=
                current_shares,
        )

    current_price = float(
        capital_gate.get(
            "current_price"
        )
        or 0.0
    )

    minimum_price = float(
        authorization.get(
            "minimum_order_price"
        )
        or 0.0
    )

    maximum_price = float(
        authorization.get(
            "maximum_order_price"
        )
        or 0.0
    )

    if (
        current_price <= 0
        or minimum_price <= 0
        or maximum_price <= 0
        or current_price < minimum_price
        or current_price > maximum_price
    ):
        return _blocked(
            case_id=case_id,
            reason=
                "ORDER_PRICE_OUTSIDE_AUTHORIZED_WINDOW",
            authorization_id=
                authorization_id,

            current_price=
                current_price,

            minimum_order_price=
                minimum_price,

            maximum_order_price=
                maximum_price,
        )

    current_notional = float(
        sizing.get(
            "proposed_notional"
        )
        or 0.0
    )

    expected_notional = (
        authorized_shares
        * current_price
    )

    if abs(
        current_notional
        - expected_notional
    ) > 0.02:
        return _blocked(
            case_id=case_id,
            reason=
                "CURRENT_NOTIONAL_INCONSISTENT",
            authorization_id=
                authorization_id,
        )

    max_notional = float(
        authorization.get(
            "authorized_max_notional"
        )
        or 0.0
    )

    if (
        max_notional <= 0
        or current_notional
        > max_notional + 0.01
    ):
        return _blocked(
            case_id=case_id,
            reason=
                "AUTHORIZED_NOTIONAL_EXCEEDED",
            authorization_id=
                authorization_id,

            current_notional=
                current_notional,

            authorized_max_notional=
                max_notional,
        )

    consumed = (
        consume_verified_paper_authorization(
            authorization_id=
                authorization_id,

            current_binding=
                current_binding,
        )
    )

    if not consumed.get("consumed"):
        return _blocked(
            case_id=case_id,
            reason=str(
                consumed.get("reason")
                or
                "AUTHORIZATION_CONSUME_FAILED"
            ),
            authorization_id=
                authorization_id,
        )

    execution_id = (
        f"governed_paper_"
        f"{uuid4().hex}"
    )

    execution = {
        "execution_id":
            execution_id,

        "case_id":
            case_id,

        "paper_authorization_id":
            authorization_id,

        "status":
            "COMPLETE",

        "execution":
            "PAPER_ORDER_CREATED",

        "shares":
            authorized_shares,

        "entry_price":
            round(
                current_price,
                4,
            ),

        "notional":
            round(
                current_notional,
                2,
            ),

        "authorization_reference_price":
            authorization.get(
                "authorization_reference_price"
            ),

        "authorized_price_window": {
            "minimum":
                minimum_price,
            "maximum":
                maximum_price,
        },

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

        "capital_reward_risk":
            float(
                capital_gate.get(
                    "reward_risk"
                )
            ),

        "thesis_status":
            thesis_status.get("status"),

        "authorization_binding_sha256":
            authorization.get(
                "binding_sha256"
            ),

        "authorization_consumed":
            True,

        "paper_mode":
            True,

        # Permission applies only to this recorded
        # paper order.
        "paper_order_permission":
            True,

        # Real capital is still impossible.
        "trade_execution_permission":
            False,

        "live_execution":
            False,

        "created_at":
            utc_now(),
    }

    record_object(
        execution_id,
        "governed_paper_execution",
        case_id,
        execution,
        parent_id=authorization_id,
    )

    record_event(
        case_id,
        "GOVERNED_PAPER_ORDER_CREATED",
        entity_id=execution_id,
        payload={
            "paper_authorization_id":
                authorization_id,

            "shares":
                authorized_shares,

            "entry_price":
                current_price,

            "notional":
                current_notional,

            "authorization_consumed":
                True,

            "paper_mode":
                True,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        },
    )

    return execution
