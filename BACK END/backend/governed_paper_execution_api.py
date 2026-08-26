from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from governed_paper_execution_bridge import (
    create_governed_paper_order,
)
from ledger import (
    latest_object,
    paper_authorization_consumed,
)
from paper_authorization_api import (
    _current_state,
)


router = APIRouter()


def _authorization_id(
    payload: dict[str, Any],
) -> str:
    authorization_id = str(
        payload.get(
            "paper_authorization_id"
        )
        or ""
    ).strip()

    if not authorization_id:
        raise ValueError(
            "paper_authorization_id is required"
        )

    if not authorization_id.startswith(
        "paper_auth_"
    ):
        raise ValueError(
            "paper_authorization_id must be "
            "a governed paper_auth_* token"
        )

    return authorization_id


@router.get(
    "/governed-paper-execution/{case_id}/status"
)
def governed_paper_execution_status(
    case_id: str,
):
    latest_execution = latest_object(
        "governed_paper_execution",
        case_id=case_id,
    ) or {}

    latest_authorization = latest_object(
        "paper_authorization",
        case_id=case_id,
    ) or {}

    auth_id = latest_authorization.get(
        "paper_authorization_id"
    )

    consumed = (
        paper_authorization_consumed(
            auth_id
        )
        if auth_id
        else None
    )

    return {
        "case_id":
            case_id,

        "latest_authorization": {
            "paper_authorization_id":
                auth_id,

            "consumed":
                consumed,

            "authorized_shares":
                latest_authorization.get(
                    "authorized_shares"
                ),

            "authorized_notional":
                latest_authorization.get(
                    "authorized_notional"
                ),
        },

        "latest_paper_execution": {
            "execution_id":
                latest_execution.get(
                    "execution_id"
                ),

            "status":
                latest_execution.get(
                    "status"
                ),

            "execution":
                latest_execution.get(
                    "execution"
                ),

            "shares":
                latest_execution.get(
                    "shares"
                ),

            "notional":
                latest_execution.get(
                    "notional"
                ),

            "entry_price":
                latest_execution.get(
                    "entry_price"
                ),
        },

        "paper_mode":
            True,

        "live_execution":
            False,

        "trade_execution_permission":
            False,
    }


@router.post(
    "/governed-paper-execution/{case_id}/submit"
)
def submit_governed_paper_order(
    case_id: str,
    payload: dict[str, Any],
):
    """
    Final API bridge into PAPER execution only.

    This endpoint NEVER:
      - creates an authorization,
      - changes sizing,
      - connects to a broker,
      - submits live capital.
    """

    try:
        authorization_id = (
            _authorization_id(
                payload
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # Submission always refreshes current market,
    # Capital and sizing state before token verification.
    state = _current_state(
        case_id,
        refresh_market=True,
    )

    result = create_governed_paper_order(
        case_id=case_id,

        authorization_id=
            authorization_id,

        qualification=state[
            "qualification"
        ],

        thesis_status=state[
            "thesis"
        ],

        capital_gate=state[
            "capital"
        ],

        sizing=state[
            "sizing"
        ],
    )

    if (
        result.get("execution")
        != "PAPER_ORDER_CREATED"
    ):
        raise HTTPException(
            status_code=409,
            detail=result,
        )

    return result
