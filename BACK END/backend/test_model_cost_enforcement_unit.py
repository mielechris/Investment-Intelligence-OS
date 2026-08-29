from __future__ import annotations

import json
from pathlib import Path

import model_cost_enforcement as cost


def _use_tmp(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("IIOS_MODEL_COST_DIR", str(tmp_path))
    return tmp_path


def test_first_call_allowed_then_duplicate_deferred(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    first = cost.preflight_xai_request(query="MU HBM demand", model="grok-4.6", case_id="MU", estimated_input_tokens=500)
    assert first["allow"] is True
    fake = {
        "usage": {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 200,
            "num_server_side_tools_used": 2,
            "cost_in_usd_ticks": 125000000,
        }
    }
    row = cost.record_xai_response(fake, model="grok-4.6", query="MU HBM demand", case_id="MU", latency_ms=1200)
    assert row["cost_usd"] == 0.0125
    assert row["input_tokens"] == 1000
    assert row["cached_input_tokens"] == 800
    assert row["x_search_calls"] == 2
    second = cost.preflight_xai_request(query="MU HBM demand", model="grok-4.6", case_id="MU", estimated_input_tokens=500)
    assert second["allow"] is False
    assert second["decision"] == "DEFER_DUPLICATE"


def test_hard_budget_blocks_without_prompt_or_key_persistence(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    monkeypatch.setenv("XAI_API_KEY", "secret-never-persist")
    ledger = tmp_path / cost.LEDGER_NAME
    ledger.write_text(json.dumps({
        "timestamp": cost._iso(cost._utc_now()),
        "provider": "XAI",
        "model": "grok-4.6",
        "task_type": "GROK_X_SEARCH",
        "case_id": "A",
        "cost_usd": 25.0,
        "query_fingerprint": "different",
    }) + "\n", encoding="utf-8")
    result = cost.preflight_xai_request(query="sensitive prompt text", model="grok-4.6", case_id="B", estimated_input_tokens=100)
    assert result["allow"] is False
    assert result["decision"] == "BLOCK_HARD_BUDGET"
    persisted = (tmp_path / cost.ADMISSION_LEDGER_NAME).read_text(encoding="utf-8")
    assert "sensitive prompt text" not in persisted
    assert "secret-never-persist" not in persisted


def test_context_limit_is_binding(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    result = cost.preflight_xai_request(query="large context", model="grok-4.6", estimated_input_tokens=16001)
    assert result["allow"] is False
    assert result["decision"] == "DEFER_CONTEXT_LIMIT"


def test_hook_registry_and_artifact_are_active(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    hook = cost.register_hook()
    artifact = json.loads((tmp_path / cost.ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert hook["hooks"]["xai_grok_social_intelligence"]["binding"] is True
    assert artifact["status"] == "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE"
    assert artifact["enforcement_hooks_connected"] is True
    assert artifact["trade_execution_permission"] is False if "trade_execution_permission" in artifact else artifact["safety"]["trade_execution_permission"] is False
    assert artifact["safety"]["capital_authority"] is False
    assert artifact["safety"]["live_execution"] is False
