from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import grok_provider  # noqa: E402


def _install_fake_governor(*, allow: bool):
    events = {"responses": [], "failures": [], "requests": []}

    def preflight(**kwargs):
        return {
            "allow": allow,
            "decision": "ALLOW" if allow else "DEFER_SOFT_BUDGET",
            "reasons": ["TEST_POLICY"],
            "binding": True,
        }

    def record_response(response, **kwargs):
        events["responses"].append((response, kwargs))
        return {"recorded": True}

    def record_failure(**kwargs):
        events["failures"].append(kwargs)
        return {"recorded": True}

    grok_provider.preflight_xai_request = preflight
    grok_provider.record_xai_response = record_response
    grok_provider.record_xai_failure = record_failure
    return events


def test_denied_preflight_never_calls_xai(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-only")
    _install_fake_governor(allow=False)

    def forbidden_request(*args, **kwargs):
        raise AssertionError("xAI network boundary must not be reached after denied admission")

    monkeypatch.setattr(grok_provider, "_request", forbidden_request)
    try:
        grok_provider.research_json(system="system", user="user")
    except RuntimeError as exc:
        assert "GROK_COST_GOVERNOR_DEFER_SOFT_BUDGET" in str(exc)
    else:
        raise AssertionError("denied admission must fail closed")


def test_allowed_request_is_bounded_and_accounted(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-only")
    events = _install_fake_governor(allow=True)

    def fake_request(method, path, payload, *, timeout=grok_provider.DEFAULT_TIMEOUT_SECONDS, retries=None):
        events["requests"].append(
            {"method": method, "path": path, "payload": payload, "retries": retries}
        )
        return {
            "id": "resp_test",
            "model": "grok-4.6",
            "output_text": '{"ranked_candidates": []}',
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cost_in_usd_ticks": 123,
                "num_server_side_tools_used": 1,
            },
        }

    monkeypatch.setattr(grok_provider, "_request", fake_request)
    result = grok_provider.research_json(system="system", user="user")
    assert result["status"] == "CAPTURED"
    assert result["cost_governor_binding"] is True
    assert len(events["requests"]) == 1
    request = events["requests"][0]
    assert request["retries"] == 0
    assert request["payload"]["max_output_tokens"] == 2000
    assert request["payload"]["max_tool_calls"] == 3
    assert request["payload"]["prompt_cache_key"] == "iios-9e-grok-wire-v1"
    assert request["payload"]["store"] is False
    assert len(events["responses"]) == 1
    assert events["responses"][0][1]["task_type"] == "GROK_9E_RADAR"
    assert not events["failures"]


def test_configuration_declares_fail_closed_cost_boundary(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-only")
    _install_fake_governor(allow=True)
    status = grok_provider.configuration_status()
    assert status["configured"] is True
    assert status["cost_governor_binding"] is True
    assert status["cost_governor_ready"] is True
    assert status["request_retries"] == 0
    assert status["max_output_tokens"] == 2000
    assert status["max_server_side_tool_calls"] == 3
    assert status["prompt_cache_key_enabled"] is True
    assert status["trade_execution_permission"] is False
    assert status["live_execution"] is False
