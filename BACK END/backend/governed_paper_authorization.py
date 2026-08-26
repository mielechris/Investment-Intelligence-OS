from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
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
    "GOVERNED_PAPER_AUTHORIZATION_V2"
)

AUTHORIZATION_TTL_MINUTES = 15

MAX_UPWARD_PRICE_DRIFT_PCT = 0.005
MAX_DOWNWARD_PRICE_DRIFT_PCT = 0.05


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _capital_reward_risk_passed(
    capital_gate: dict[str, Any],
) -> bool:
    checks = capital_gate.get("checks") or {}

    if checks.get("reward_risk_passed") is True:
        return True

    reward_risk = _safe_float(
        capital_gate.get("reward_risk")
    )

    minimum = _safe_float(
        capital_gate.get(
            "minimum_reward_risk"
        )
    )

    return (
        capital_gate.get("decision") == "APPROVED"
        and minimum > 0
        and reward_risk >= minimum
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
    Stable authorization fingerprint.

    IMPORTANT:
    Current market price and current notional are NOT
    included here. They are governed separately through
    the authorization's explicit paper-order price window.

    This allows a small permitted market-price move while
    keeping the exact case, research state, thesis,
    sizing, invalidation, portfolio NAV and risk policy
    cryptographically bound.
    """

    return {
        "binding_version":
            "PAPER_AUTH_BINDING_V2",

        "case_id":
            str(case_id),

        "qualification_assessment_id":
            qualification.get(
                "qualification_assessment_id"
            ),

        "research_stage":
            qualification.get("stage"),

        "qualified_buy_candidate":
            qualification.get(
                "qualified_buy_candidate"
            ),

        "risk_authorization_id":
            capital_gate.get(
                "_risk_authorization_id"
            ),

        "thesis_status":
            thesis_status.get("status"),

        "thesis_invalidated":
            thesis_status.get(
                "thesis_invalidated"
            ),

        "thesis_breached_rules":
            sorted(
                str(item)
                for item in (
                    thesis_status.get(
                        "breached_rules"
                    )
                    or []
                )
            ),

        "capital_decision":
            capital_gate.get("decision"),

        "capital_minimum_reward_risk":
            capital_gate.get(
                "minimum_reward_risk"
            ),

        "capital_maximum_qualifying_entry":
            capital_gate.get(
                "maximum_qualifying_entry"
            ),

        "capital_upside_reference_value":
            capital_gate.get(
                "upside_reference_value"
            ),

        "capital_downside_reference_value":
            capital_gate.get(
                "downside_reference_value"
            ),

        "sizing_decision":
            sizing.get("decision"),

        "proposed_shares":
            sizing.get("proposed_shares"),

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

        "max_position_pct":
            sizing.get("max_position_pct"),

        "max_portfolio_risk_pct":
            sizing.get(
                "max_portfolio_risk_pct"
            ),

        "generic_sizing_profile_id":
            sizing.get(
                "generic_sizing_profile_id"
            ),

        "invalidation_mode":
            sizing.get(
                "invalidation_mode"
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


def _parse_time(
    value: Any,
) -> datetime | None:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def paper_authorization_expired(
    authorization: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    expires = _parse_time(
        authorization.get("expires_at")
    )

    if expires is None:
        return True

    now = (
        now
        or datetime.now(timezone.utc)
    )

    return now >= expires


def create_paper_authorization(
    *,
    case_id: str,
    qualification: dict[str, Any],
    thesis_status: dict[str, Any],
    capital_gate: dict[str, Any],
    sizing: dict[str, Any],
) -> dict[str, Any]:

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

        "capital_reward_risk_passed":
            _capital_reward_risk_passed(
                capital_gate
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
            and sizing.get(
                "live_execution"
            )
            is False
        ),
    }

    failed = [
        key
        for key, passed
        in checks.items()
        if not passed
    ]

    if failed:
        return {
            "decision":
                "AUTHORIZATION_DENIED",

            "failed_checks":
                failed,

            "checks":
                checks,

            "paper_authorization_id":
                None,

            "paper_execution_ready":
                False,

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        }

    reference_price = _safe_float(
        capital_gate.get("current_price")
    )

    if reference_price <= 0:
        return {
            "decision":
                "AUTHORIZATION_DENIED",

            "failed_checks": [
                "valid_reference_price"
            ],

            "checks":
                checks,

            "paper_authorization_id":
                None,

            "paper_execution_ready":
                False,

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
                False,
        }

    maximum_qualifying_entry = (
        _safe_float(
            capital_gate.get(
                "maximum_qualifying_entry"
            )
        )
    )

    upper_by_slippage = (
        reference_price
        * (
            1.0
            + MAX_UPWARD_PRICE_DRIFT_PCT
        )
    )

    if maximum_qualifying_entry > 0:
        maximum_order_price = min(
            upper_by_slippage,
            maximum_qualifying_entry,
        )
    else:
        maximum_order_price = (
            upper_by_slippage
        )

    minimum_order_price = (
        reference_price
        * (
            1.0
            - MAX_DOWNWARD_PRICE_DRIFT_PCT
        )
    )

    shares = int(
        sizing.get(
            "proposed_shares"
        )
    )

    reference_notional = (
        shares * reference_price
    )

    maximum_notional = (
        shares * maximum_order_price
    )

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

    created_dt = datetime.now(
        timezone.utc
    )

    expires_dt = (
        created_dt
        + timedelta(
            minutes=
                AUTHORIZATION_TTL_MINUTES
        )
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

        # Exact authorized sizing.
        "authorized_shares":
            shares,

        "authorized_notional":
            round(
                reference_notional,
                2,
            ),

        "authorized_max_notional":
            round(
                maximum_notional,
                2,
            ),

        # Explicit paper-order price envelope.
        "authorization_reference_price":
            round(
                reference_price,
                4,
            ),

        "minimum_order_price":
            round(
                minimum_order_price,
                4,
            ),

        "maximum_order_price":
            round(
                maximum_order_price,
                4,
            ),

        "maximum_qualifying_entry":
            round(
                maximum_qualifying_entry,
                4,
            )
            if maximum_qualifying_entry > 0
            else None,

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

        "authorization_ttl_minutes":
            AUTHORIZATION_TTL_MINUTES,

        "created_at":
            created_dt.isoformat(),

        "expires_at":
            expires_dt.isoformat(),

        # Token alone still cannot create an order.
        "paper_execution_ready":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
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
                shares,

            "minimum_order_price":
                authorization[
                    "minimum_order_price"
                ],

            "maximum_order_price":
                authorization[
                    "maximum_order_price"
                ],

            "expires_at":
                authorization[
                    "expires_at"
                ],

            "paper_order_permission":
                False,

            "trade_execution_permission":
                False,

            "live_execution":
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

    if (
        authorization.get(
            "authorization_version"
        )
        != AUTHORIZATION_VERSION
    ):
        return {
            "valid": False,
            "reason":
                "UNSUPPORTED_AUTHORIZATION_VERSION",
        }

    if paper_authorization_expired(
        authorization
    ):
        return {
            "valid": False,
            "reason":
                "AUTHORIZATION_EXPIRED",
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
        "valid":
            True,

        "reason":
            None,

        "paper_authorization_id":
            authorization_id,

        "binding_sha256":
            actual,

        "authorized_shares":
            authorization.get(
                "authorized_shares"
            ),

        "minimum_order_price":
            authorization.get(
                "minimum_order_price"
            ),

        "maximum_order_price":
            authorization.get(
                "maximum_order_price"
            ),

        "expires_at":
            authorization.get(
                "expires_at"
            ),

        "paper_execution_ready":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
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

    consumed = (
        consume_paper_authorization(
            authorization_id
        )
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

        # Consumption is not broker execution.
        "paper_execution_ready":
            False,

        "paper_order_permission":
            False,

        "trade_execution_permission":
            False,

        "live_execution":
            False,
    }
