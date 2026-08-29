from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import agent_contract_v2  # noqa: E402
import eight_agent_orchestrator_v2  # noqa: E402
import high_speed_gemini_deep_worker  # noqa: E402
import model_agent_health_watchdog  # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self.output_text = json.dumps(payload)


class _FakeResponses:
    def __init__(self, events, payload):
        self.events = events
        self.payload = payload

    def create(self, **kwargs):
        self.events.append(kwargs)
        return _FakeResponse(self.payload)


class _FakeClient:
    def __init__(self, events, payload):
        self.responses = _FakeResponses(events, payload)


def test_agent_contract_v2_one_call_and_evidence_linkage(monkeypatch):
    events = []
    payload = {
        "headline": "Policy transmission is plausible but not complete",
        "view": "Evidence supports a policy catalyst, while timing remains uncertain.",
        "confidence": 0.71,
        "disposition": "WATCH",
        "missing_evidence": ["implementation timing"],
        "falsifier": "Policy implementation is delayed.",
        "floor_comment": "The memo exists; the money still has to move.",
        "key_claims": [
            {
                "claim": "The policy action was announced.",
                "evidence_ids": ["evidence_good", "invented_id"],
                "confidence": 0.9,
                "direction": "bullish",
                "inference": False,
            }
        ],
        "catalyst_timeline": ["Next implementation milestone"],
        "scenarios": {
            "bull": {"case": "Fast implementation", "probability": 0.3, "drivers": ["funding"], "invalidators": ["delay"]},
            "base": {"case": "Gradual implementation", "probability": 0.5, "drivers": ["normal process"], "invalidators": ["reversal"]},
            "bear": {"case": "Implementation stalls", "probability": 0.2, "drivers": ["delay"], "invalidators": ["signed contracts"]},
        },
        "confidence_components": {
            "evidence_quality": 0.8,
            "causal_strength": 0.6,
            "timing_clarity": 0.5,
            "contradiction_resilience": 0.7,
        },
        "contradictions": ["Timing remains uncertain"],
        "missing_evidence_ranked": ["implementation timing"],
        "falsifiers": ["Policy implementation is delayed."],
        "questions_for_other_desks": ["Does price already discount the catalyst?"],
        "risk_flags": ["TIMING_UNCERTAINTY"],
    }
    monkeypatch.setattr(agent_contract_v2, "OpenAI", lambda: _FakeClient(events, payload))
    result = agent_contract_v2.run_specialist_v2(
        "policy",
        "TEST",
        [
            {
                "evidence_id": "evidence_good",
                "claim": "Policy announcement",
                "quality_score": 0.9,
                "freshness_score": 0.9,
                "reliability_score": 0.95,
                "stale": False,
                "missing_fields": [],
            }
        ],
    )
    assert len(events) == 1
    assert result["contract_version"] == "batch10m1-agent-contract-v2"
    assert result["headline"]
    assert result["view"]
    assert result["missing_evidence"]
    assert result["falsifier"]
    assert result["key_claims"][0]["evidence_ids"] == ["evidence_good"]
    assert result["invalid_evidence_references"] == ["invented_id"]
    assert result["evidence_linkage_ratio"] == 1.0
    assert result["trade_execution_permission"] is False
    assert result["live_execution"] is False


def test_orchestrator_v2_preserves_call_topology():
    plan = eight_agent_orchestrator_v2.agent_wave_plan()
    assert len(plan["all_agents"]) == 8
    assert plan["specialist_call_count"] == 8
    assert plan["committee_call_count"] == 1
    assert plan["extra_model_calls_added"] == 0
    assert plan["trade_execution_permission"] is False
    assert plan["live_execution"] is False


def test_gemini_pro_prioritizes_flash_open_questions():
    request = {
        "source_context": {
            "gemini": {
                "open_questions": ["Is demand durable?", "Is the catalyst already priced?"],
                "counterevidence": ["Margins weakened"],
            }
        }
    }
    questions = high_speed_gemini_deep_worker.priority_research_questions(request)
    assert questions == ["Is demand durable?", "Is the catalyst already priced?"]
    system, user = high_speed_gemini_deep_worker._prompt(request)
    assert "PRIORITIZE" in system
    assert "Is demand durable?" in user


def _make_health_db(path: Path):
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE ledger_objects (object_id TEXT, object_type TEXT, case_id TEXT, payload_json TEXT, created_at TEXT)"
    )
    db.execute(
        "CREATE TABLE audit_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, event_type TEXT, entity_id TEXT, payload_json TEXT, created_at TEXT)"
    )
    now = datetime.now(timezone.utc).isoformat()

    def obj(object_id, object_type, payload):
        db.execute(
            "INSERT INTO ledger_objects VALUES (?,?,?,?,?)",
            (object_id, object_type, "test", json.dumps(payload), now),
        )

    obj(
        "universe",
        "production_index_universe_snapshot",
        {
            "verified_complete": True,
            "indexes": {
                "SP500": {"symbol_count": 504},
                "NASDAQ100": {"symbol_count": 102},
            },
        },
    )
    obj(
        "radar",
        "high_speed_market_radar_state",
        {"last_cycle_id": "cycle", "last_cycle_completed_at": now, "provider_errors": {}},
    )
    obj(
        "deep",
        "high_speed_gemini_deep_worker_state",
        {"status": "IDLE", "queue_depth": 0, "processed": False, "created_at": now},
    )
    obj(
        "floor",
        "high_speed_case_floor_state",
        {
            "last_cycle_completed_at": now,
            "queue_depth_before": 0,
            "selected_count": 0,
            "completed_count": 0,
            "failed_closed_count": 0,
            "remaining_queue_depth": 0,
            "agent_contract_version": "batch10m1-agent-contract-v2",
        },
    )
    db.commit()
    db.close()


def test_health_watchdog_recognizes_healthy_idle(tmp_path):
    db_path = tmp_path / "ledger.db"
    _make_health_db(db_path)
    health = model_agent_health_watchdog.build_health_snapshot(db_path)
    assert health["status"] == "MODEL_AGENT_INTELLIGENCE_HEALTH_ACTIVE"
    assert health["overall_state"] in {"HEALTHY", "IDLE_HEALTHY"}
    states = {row["component"]: row["state"] for row in health["components"]}
    assert states["STRICT_GOVERNED_UNIVERSE"] == "HEALTHY"
    assert states["9E_RADAR"] == "HEALTHY"
    assert states["GEMINI_PRO_DEEP_WORKER"] == "IDLE_HEALTHY"
    assert states["GPT_EIGHT_AGENT_CASE_FLOOR"] == "IDLE_HEALTHY"
    assert health["provider_requests_made"] is False
    assert health["ledger_mutated"] is False
    assert health["trade_execution_permission"] is False
    assert health["live_execution"] is False


def test_health_watchdog_surfaces_recent_model_failure(tmp_path):
    db_path = tmp_path / "ledger.db"
    _make_health_db(db_path)
    db = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO audit_events(case_id,event_type,entity_id,payload_json,created_at) VALUES (?,?,?,?,?)",
        ("radar", "HIGH_SPEED_MODEL_RESEARCH_FAILED_CLOSED", "x", json.dumps({"error": "TEST"}), now),
    )
    db.commit()
    db.close()
    health = model_agent_health_watchdog.build_health_snapshot(db_path)
    assert "MODEL_RESEARCH_RECENT_FAILURES" in health["issues"]
    model = next(row for row in health["components"] if row["component"] == "GROK_GEMINI_MODEL_CONTEXT")
    assert model["state"] == "DEGRADED"


def test_launcher_bounds_gemini_and_preserves_paper_safety():
    text = (ROOT / "scripts" / "launch_batch9e_live_paper_factory.py").read_text(encoding="utf-8")
    assert '"IIOS_9E_GEMINI_FINALISTS": "6"' in text
    assert '"IIOS_9E_GEMINI_WORKERS": "2"' in text
    assert '"IIOS_GEMINI_RETRIES": "0"' in text
    assert 'BRANCH = "feature/batch10m1-model-agent-intelligence-health"' in text
    assert "Broker connected: FALSE" in text
    assert "Live execution: FALSE" in text


def test_no_extra_execution_authority_in_superbatch_sources():
    paths = [
        BACKEND / "agent_contract_v2.py",
        BACKEND / "eight_agent_orchestrator_v2.py",
        BACKEND / "model_agent_health_watchdog.py",
        BACKEND / "high_speed_case_queue.py",
        BACKEND / "high_speed_gemini_deep_worker.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert '"trade_execution_permission": True' not in text
        assert '"live_execution": True' not in text
        assert '"capital_authority": True' not in text
