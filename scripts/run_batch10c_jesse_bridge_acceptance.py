#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import ledger  # noqa: E402
from ledger import get_object, latest_object, record_object, utc_now  # noqa: E402
import opportunity_dispatch  # noqa: E402
from opportunity_acquisition import OPPORTUNITY_LEDGER_CASE  # noqa: E402
from jesse_paper_fund_bridge import dispatch_jesse_top_three  # noqa: E402
import governed_paper_trading_controller as paper_controller  # noqa: E402


def count_objects(db_path: Path, object_type: str) -> int:
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT COUNT(*) FROM ledger_objects WHERE object_type = ?",
            (object_type,),
        ).fetchone()
    return int(row[0]) if row else 0


def fake_eight_agent_orchestration(case_id: str):
    orchestration_id = "orchestration_acceptance"
    decision_id = "decision_acceptance"
    orchestration = {
        "orchestration_id": orchestration_id,
        "case_id": case_id,
        "status": "COMPLETE",
        "specialist_count": 8,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    committee = {
        "decision_id": decision_id,
        "case_id": case_id,
        "status": "complete",
        "disposition": "WATCH",
        "confidence": 0.82,
        "paper_mode": True,
        "trade_execution_permission": False,
        "live_execution": False,
        "created_at": utc_now(),
    }
    record_object(
        orchestration_id,
        "agent_orchestration",
        case_id,
        orchestration,
    )
    record_object(
        decision_id,
        "committee_decision",
        case_id,
        committee,
        parent_id=orchestration_id,
    )
    return {
        "orchestration": orchestration,
        "committee": committee,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="iios_batch10c_acceptance_") as temp_dir:
        db_path = Path(temp_dir) / "acceptance.db"

        # All ledger reads/writes are redirected to this isolated database.
        ledger.DB_PATH = db_path
        ledger.init_ledger()

        candidates = [
            {
                "opportunity_candidate_id": "opportunity_acceptance_1",
                "ticker": "AAA",
                "label": "Acceptance Alpha",
                "query": "Acceptance Alpha AAA",
                "score": 88.0,
                "priority": "HIGH",
                "eligible_for_promotion": True,
                "reason_codes": ["POSITIVE_FCF", "POSSIBLE_TEMPORARY_DISLOCATION"],
                "catalyst_categories": ["DISLOCATION"],
                "evidence": [],
                "evidence_count": 0,
                "promoted_case_id": None,
                "created_by": "DISLOCATION_SCANNER_V1",
                "paper_mode": True,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": utc_now(),
            },
            {
                "opportunity_candidate_id": "opportunity_acceptance_2",
                "ticker": "BBB",
                "label": "Acceptance Beta",
                "query": "Acceptance Beta BBB",
                "score": 61.0,
                "priority": "MEDIUM",
                "eligible_for_promotion": False,
                "reason_codes": ["UNRESOLVED"],
                "catalyst_categories": ["DISLOCATION"],
                "evidence": [],
                "evidence_count": 0,
                "promoted_case_id": None,
                "created_by": "DISLOCATION_SCANNER_V1",
                "paper_mode": True,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": utc_now(),
            },
            {
                "opportunity_candidate_id": "opportunity_acceptance_3",
                "ticker": "CCC",
                "label": "Acceptance Gamma",
                "query": "Acceptance Gamma CCC",
                "score": 91.0,
                "priority": "HIGH",
                "eligible_for_promotion": True,
                "reason_codes": ["OTHER_SOURCE"],
                "catalyst_categories": ["DISLOCATION"],
                "evidence": [],
                "evidence_count": 0,
                "promoted_case_id": None,
                "created_by": "OTHER_SCANNER",
                "paper_mode": True,
                "paper_order_permission": False,
                "trade_execution_permission": False,
                "live_execution": False,
                "created_at": utc_now(),
            },
        ]

        for candidate in candidates:
            record_object(
                candidate["opportunity_candidate_id"],
                "opportunity_candidate",
                OPPORTUNITY_LEDGER_CASE,
                candidate,
                topic=candidate["label"],
            )

        scan = {
            "dislocation_scan_id": "dislocation_acceptance",
            "opportunity_candidate_ids": [
                candidate["opportunity_candidate_id"] for candidate in candidates
            ],
            "top_three": [
                {"ticker": "AAA"},
                {"ticker": "BBB"},
                {"ticker": "CCC"},
            ],
            "paper_mode": True,
            "trade_execution_permission": False,
            "live_execution": False,
            "created_at": utc_now(),
        }

        with patch.object(
            opportunity_dispatch,
            "run_eight_agent_orchestration",
            side_effect=fake_eight_agent_orchestration,
        ):
            bridge_result = dispatch_jesse_top_three(scan)

        dispatched = [
            row for row in bridge_result.get("results") or []
            if row.get("status") == "DISPATCHED"
        ]
        if len(dispatched) != 1:
            raise AssertionError(
                f"Expected exactly one dispatched Jesse candidate, got {len(dispatched)}"
            )

        case_id = str(dispatched[0].get("case_id") or "")
        if not case_id.startswith("case_"):
            raise AssertionError(f"Governed case was not created: {case_id!r}")

        case = get_object(case_id)
        committee = latest_object("committee_decision", case_id=case_id)
        orchestration = latest_object("agent_orchestration", case_id=case_id)
        if not case or not committee or not orchestration:
            raise AssertionError("Case / eight-agent orchestration / Committee persistence incomplete")

        queue = paper_controller.governed_case_queue()
        if not any(str(row.get("case_id")) == case_id for row in queue):
            raise AssertionError("9B governed queue did not discover the Jesse-originated case")

        forbidden_counts = {
            "paper_authorization": count_objects(db_path, "paper_authorization"),
            "governed_paper_execution": count_objects(db_path, "governed_paper_execution"),
            "paper_portfolio_transaction": count_objects(db_path, "paper_portfolio_transaction"),
        }
        if any(forbidden_counts.values()):
            raise AssertionError(
                f"Jesse bridge created forbidden capital/execution objects: {forbidden_counts}"
            )

        if bridge_result.get("paper_order_permission") is not False:
            raise AssertionError("Bridge paper_order_permission must remain False")
        if bridge_result.get("trade_execution_permission") is not False:
            raise AssertionError("Bridge trade_execution_permission must remain False")
        if bridge_result.get("live_execution") is not False:
            raise AssertionError("Bridge live_execution must remain False")

        summary = {
            "result": "PASS",
            "isolated_ledger": str(db_path),
            "top_three_count": bridge_result.get("top_three_count"),
            "dispatched_count": bridge_result.get("dispatched_count"),
            "skipped_count": bridge_result.get("skipped_count"),
            "case_id": case_id,
            "orchestration_id": orchestration.get("orchestration_id"),
            "committee_disposition": committee.get("disposition"),
            "committee_confidence": committee.get("confidence"),
            "visible_to_9b_queue": True,
            "forbidden_object_counts": forbidden_counts,
            "paper_order_permission": bridge_result.get("paper_order_permission"),
            "trade_execution_permission": bridge_result.get("trade_execution_permission"),
            "live_execution": bridge_result.get("live_execution"),
        }
        print("=== BATCH 10C JESSE BRIDGE ACCEPTANCE ===")
        print(json.dumps(summary, indent=2, default=str))
        print("ACCEPTANCE: PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
