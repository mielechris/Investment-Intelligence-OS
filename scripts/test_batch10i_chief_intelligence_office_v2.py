#!/usr/bin/env python3
from __future__ import annotations

from iios_chief_intelligence_office_v2 import build_office_v2


def fixture() -> dict:
    return build_office_v2(
        legacy_office={
            "status": "CHIEF_INTELLIGENCE_OFFICE_ADVISORY_READY",
            "improvement_memo": {
                "top_five_upgrades": [
                    {
                        "upgrade_id": "RADAR_RECALL_REVIEW",
                        "title": "Improve radar recall without bypassing governance",
                        "priority_score": 100,
                        "supporting_evidence": ["9H miss rate: 52.8%"],
                        "production_shadow_research_recommendation": "SHADOW",
                    },
                    {
                        "upgrade_id": "MODEL_TASK_LEAGUE",
                        "title": "Create task-level model performance and cost scorecards",
                        "priority_score": 98,
                        "supporting_evidence": ["Model scorecard missing"],
                        "production_shadow_research_recommendation": "RESEARCH",
                    },
                ]
            },
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
                {"stage": "ARCHIVE_SEARCH", "state": "ACTIVE"},
                {"stage": "ANALOG_MATCHING", "state": "ACTIVE"},
                {"stage": "REGIME_NORMALIZATION", "state": "PARTIAL", "note": "Historical macro joins missing."},
                {"stage": "EVENT_RECONSTRUCTION", "state": "MEASUREMENT_GAP", "note": "Historical event/news corpus missing."},
                {"stage": "FORWARD_RETURN_STUDY", "state": "ACTIVE"},
            ],
        },
    )


def main() -> int:
    payload = fixture()
    assert payload["status"] == "CHIEF_INTELLIGENCE_OFFICE_V2_WHOLE_STACK_ADVISORY_READY"
    assert payload["whole_stack_inputs_observed"] == payload["whole_stack_input_count"] == 10
    ranked = payload["ranked_upgrades"]
    ids = [row["upgrade_id"] for row in ranked]
    assert ids[0] == "HISTORICAL_EVENT_RECONSTRUCTION", ids
    assert "HISTORICAL_REGIME_LIBRARY" in ids
    assert "BENCHMARK_ALPHA_ATTRIBUTION" in ids
    assert "DATA_HEALTH_WATCHDOG" in ids
    assert "PAPER_EVIDENCE_CAMPAIGN" in ids
    paper = next(row for row in ranked if row["upgrade_id"] == "PAPER_EVIDENCE_CAMPAIGN")
    assert paper["action_class"] == "WAIT_FOR_EVIDENCE"
    historical = payload["historical_diagnostics"]
    assert historical["studies_ready"] == 8
    assert historical["event_reconstruction_state"] == "MEASUREMENT_GAP"
    assert historical["regime_normalization_state"] == "PARTIAL"
    safety = payload["safety"]
    for key in (
        "auto_apply_recommendations",
        "auto_change_thresholds",
        "auto_change_agent_weights",
        "auto_change_model_routing",
        "provider_change_authority",
        "committee_change_authority",
        "risk_rule_change_authority",
        "broker_connection_authority",
        "capital_authority",
        "trade_execution_permission",
        "live_execution",
    ):
        assert safety[key] is False, key
    assert safety["advisory_only"] is True
    assert safety["human_approval_required"] is True
    print("BATCH10I_CHIEF_INTELLIGENCE_OFFICE_V2_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
