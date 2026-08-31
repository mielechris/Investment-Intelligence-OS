#!/usr/bin/env python3
from __future__ import annotations

from iios_scientific_measurement_superbatch import (
    build_case_flow,
    build_model_task_league,
    build_validation_misses,
)


def test_case_flow_working_as_designed() -> None:
    telemetry = {
        "recent_promotions": [
            {
                "case_id": "case_1",
                "ticker": "ABC",
                "agents": {"completed_count": 8, "eight_agent_complete": True},
                "committee": {"disposition": "NO_TRADE", "confidence": 0.91},
                "risk": {"decision": "VETOED"},
                "paper_execution": {},
            },
            {
                "case_id": "case_2",
                "ticker": "XYZ",
                "agents": {"completed_count": 8, "eight_agent_complete": True},
                "committee": {"disposition": "WATCH", "confidence": 0.44},
                "risk": {},
                "paper_execution": {},
            },
        ]
    }
    result = build_case_flow(telemetry)
    assert result["state"] == "WORKING_AS_DESIGNED"
    assert result["eight_agent_complete_count"] == 2
    assert result["committee_complete_count"] == 2
    assert result["paper_execution_count"] == 0
    assert result["committee_dispositions"] == {"NO_TRADE": 1, "WATCH": 1}


def test_case_flow_detects_execution_without_risk() -> None:
    telemetry = {
        "recent_promotions": [
            {
                "case_id": "bad",
                "ticker": "BAD",
                "agents": {"completed_count": 8, "eight_agent_complete": True},
                "committee": {"disposition": "BUY", "confidence": 0.9},
                "risk": {},
                "paper_execution": {"status": "FILLED"},
            }
        ]
    }
    result = build_case_flow(telemetry)
    assert result["state"] == "PIPELINE_DEFECT_DETECTED"
    assert "PAPER_EXECUTION_WITHOUT_APPROVED_RISK" in result["pipeline_defects"][0]["defects"]


def test_validation_miss_plain_english_and_incomplete_guard() -> None:
    validation = {
        "benchmark_complete": False,
        "metrics": {
            "opportunity_count": 40,
            "detected_count": 25,
            "opportunity_miss_rate_pct": 37.5,
        },
        "missed_opportunities": [{"ticker": "MISS", "move_pct": 5.0}],
    }
    result = build_validation_misses(validation)
    assert result["evidence_state"] == "INCOMPLETE_BENCHMARK_DO_NOT_TUNE"
    assert result["validation_miss_count"] == 1
    assert "does NOT automatically mean IIOS lost money" in result["plain_english_definition"]


def test_model_task_league_measures_cost_latency_not_accuracy() -> None:
    events = [
        {
            "provider": "XAI",
            "model": "grok",
            "task_type": "RADAR_RESEARCH",
            "cost_usd": 0.10,
            "latency_ms": 1000,
            "input_tokens": 100,
            "output_tokens": 50,
        },
        {
            "provider": "XAI",
            "model": "grok",
            "task_type": "RADAR_RESEARCH",
            "cost_usd": 0.20,
            "latency_ms": 2000,
            "input_tokens": 200,
            "output_tokens": 75,
        },
    ]
    result = build_model_task_league(events, {"status": "HEALTHY"}, {"outcome_count": 2})
    row = result["task_rows"][0]
    assert result["status"] == "MODEL_TASK_LEAGUE_MEASURING"
    assert row["requests"] == 2
    assert row["average_latency_ms"] == 1500.0
    assert row["exact_cost_usd"] == 0.3
    assert row["accuracy_score"] is None
    assert row["accuracy_state"] == "MEASUREMENT_GAP_OUTCOME_LINK_NOT_PERSISTED"


def main() -> int:
    test_case_flow_working_as_designed()
    test_case_flow_detects_execution_without_risk()
    test_validation_miss_plain_english_and_incomplete_guard()
    test_model_task_league_measures_cost_latency_not_accuracy()
    print("Batch 10M.2 scientific measurement superbatch: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
