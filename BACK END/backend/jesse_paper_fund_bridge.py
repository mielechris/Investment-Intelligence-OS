from __future__ import annotations

from typing import Any
from uuid import uuid4

from ledger import get_object, latest_object, record_event, record_object, utc_now
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE
from opportunity_dispatch import dispatch_candidate


POLICY_VERSION = "batch10c-jesse-paper-fund-bridge-v1"
BRIDGE_OBJECT_TYPE = "jesse_paper_fund_bridge_run"
MAX_JESSE_CANDIDATES = 3


def dispatch_jesse_top_three(scan: dict[str, Any] | None) -> dict[str, Any]:
    """Dispatch only Jesse's current Top-3 dislocation candidates into the
    existing governed research floor.

    This bridge can create governed research cases and run the existing eight
    agent + Committee orchestration. It cannot authorize capital, size a
    position, create a paper order, or execute live capital. 9B remains the
    only path from governed cases toward the paper fund.
    """

    scan = scan if isinstance(scan, dict) else {}
    scan_id = str(scan.get("dislocation_scan_id") or "").strip()
    candidate_ids = [
        str(value).strip()
        for value in (scan.get("opportunity_candidate_ids") or [])[:MAX_JESSE_CANDIDATES]
        if str(value).strip()
    ]

    results: list[dict[str, Any]] = []

    for candidate_id in candidate_ids:
        candidate = get_object(candidate_id) or {}
        ticker = str(candidate.get("ticker") or "").strip().upper() or None

        if candidate.get("created_by") != "DISLOCATION_SCANNER_V1":
            results.append(
                {
                    "candidate_id": candidate_id,
                    "ticker": ticker,
                    "status": "SKIPPED_NOT_JESSE_DISLOCATION",
                    "case_id": None,
                }
            )
            continue

        if candidate.get("eligible_for_promotion") is not True:
            results.append(
                {
                    "candidate_id": candidate_id,
                    "ticker": ticker,
                    "status": "SKIPPED_RESEARCH_GATE",
                    "case_id": None,
                    "reason_codes": candidate.get("reason_codes") or [],
                }
            )
            continue

        try:
            dispatched = dispatch_candidate(candidate_id)
            case = dispatched.get("case") or {}
            case_id = str(case.get("case_id") or "").strip() or None
            committee = (
                latest_object("committee_decision", case_id=case_id)
                if case_id
                else None
            ) or dispatched.get("committee") or {}
            orchestration = dispatched.get("orchestration") or {}

            results.append(
                {
                    "candidate_id": candidate_id,
                    "ticker": ticker,
                    "status": "DISPATCHED",
                    "case_id": case_id,
                    "already_dispatched": bool(dispatched.get("already_dispatched")),
                    "orchestration_id": orchestration.get("orchestration_id"),
                    "committee_disposition": committee.get("disposition"),
                    "committee_confidence": committee.get("confidence"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "candidate_id": candidate_id,
                    "ticker": ticker,
                    "status": "ERROR",
                    "case_id": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    run_id = f"jesse_bridge_{uuid4().hex}"
    dispatched_count = sum(1 for row in results if row.get("status") == "DISPATCHED")
    skipped_count = sum(1 for row in results if str(row.get("status") or "").startswith("SKIPPED"))
    error_count = sum(1 for row in results if row.get("status") == "ERROR")

    payload = {
        "jesse_paper_fund_bridge_run_id": run_id,
        "policy_version": POLICY_VERSION,
        "dislocation_scan_id": scan_id or None,
        "top_three_count": len(candidate_ids),
        "dispatched_count": dispatched_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "results": results,
        "next_owner": "BATCH_9B_GOVERNED_PAPER_TRADING",
        "authority_scope": "RESEARCH_DISPATCH_ONLY",
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }

    record_object(
        run_id,
        BRIDGE_OBJECT_TYPE,
        OPPORTUNITY_LEDGER_CASE,
        payload,
        topic="JESSE_DISLOCATION",
    )
    record_event(
        OPPORTUNITY_LEDGER_CASE,
        "JESSE_TOP_THREE_DISPATCH_COMPLETE",
        entity_id=run_id,
        payload={
            "dislocation_scan_id": scan_id or None,
            "top_three_count": len(candidate_ids),
            "dispatched_count": dispatched_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        },
    )
    return payload


def latest_jesse_bridge_run() -> dict[str, Any] | None:
    return latest_object(BRIDGE_OBJECT_TYPE, case_id=OPPORTUNITY_LEDGER_CASE)
