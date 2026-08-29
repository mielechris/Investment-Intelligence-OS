#!/usr/bin/env python3
from __future__ import annotations

from iios_chief_intelligence_office_v2 import build_office_v2


def main() -> int:
    payload = build_office_v2(
        legacy_office={
            "status": "CHIEF_INTELLIGENCE_OFFICE_ADVISORY_READY",
            "improvement_memo": {"top_five_upgrades": [
                {"upgrade_id": "RADAR_RECALL_REVIEW", "title": "Improve radar recall", "priority_score": 100, "production_shadow_research_recommendation": "SHADOW"},
                {"upgrade_id": "MODEL_TASK_LEAGUE", "title": "Model scorecards", "priority_score": 98, "production_shadow_research_recommendation": "RESEARCH"},
            ]},
        },
        experiment_lab={"status": "EXPERIMENT_AB_LAB_ADVISORY_READY"},
        data_expansion={"status": "DATA_EXPANSION_FACTORY_ADVISORY_READY"},
        agent_league={"status": "AGENT_PERFORMANCE_LEAGUE_WARM_UP"},
        regime={"status": "MARKET_REGIME_INTELLIGENCE_WARM_UP"},
        qualification={"status": "INSUFFICIENT_PAPER_SAMPLE", "mature_5d_outcomes": 0},
        portfolio={"status": "CASH_ONLY_WARM_UP"},
        readiness={"status": "NOT_READY_FOR_LIVE_CAPITAL"},
        qualification_watch={"status": "QUALIFICATION_WATCH_ACTIVE", "qualification_progress_pct": 0.0},
        historical={
            "status": "HISTORICAL_RESEARCH_ACTIVE",
            "cycle": {"error_count": 0},
            "research_summary": {"studies_ready": 8, "targets_known": 9, "errors": []},
            "pipeline": [
                {"stage": "REGIME_NORMALIZATION", "state": "PARTIAL", "note": "Macro history missing."},
                {"stage": "EVENT_RECONSTRUCTION", "state": "MEASUREMENT_GAP", "note": "Historical events missing."},
            ],
        },
        event_reconstruction={
            "status": "HISTORICAL_EVENT_RECONSTRUCTION_ACTIVE",
            "research_summary": {"symbols_ready": 2, "analog_contexts_ready": 5},
        },
    )
    assert payload["whole_stack_inputs_observed"] == payload["whole_stack_input_count"] == 11
    ids = [row["upgrade_id"] for row in payload["ranked_upgrades"]]
    assert "HISTORICAL_EVENT_RECONSTRUCTION" not in ids, ids
    assert ids[0] == "HISTORICAL_REGIME_LIBRARY", ids
    historical = payload["historical_diagnostics"]
    assert historical["event_reconstruction_state"] == "ACTIVE"
    assert historical["event_symbols_ready"] == 2
    assert historical["event_analog_contexts_ready"] == 5
    assert payload["safety"]["auto_apply_recommendations"] is False
    assert payload["safety"]["live_execution"] is False
    print("BATCH10J_10I_FEEDBACK_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
