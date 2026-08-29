from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
ACTIVATOR = ROOT / "scripts" / "activate_batch10m_grok_cost_enforcement.py"
GROK_SOURCE = ROOT / "BACK END" / "backend" / "grok_social_intelligence.py"
ADAPTER = ROOT / "BACK END" / "backend" / "grok_xai_sdk_adapter.py"


def _load_activator():
    spec = importlib.util.spec_from_file_location("activate_batch10m_grok_cost_enforcement", ACTIVATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_patch_adds_binding_cost_boundary():
    module = _load_activator()
    patched = module.patch_source(GROK_SOURCE.read_text(encoding="utf-8"))
    assert "MAX_X_SEARCH_ATTEMPTS = 1" in patched
    assert '"cost_governor_binding": True' in patched
    assert '"max_server_side_tool_calls_per_request": 3' in patched
    assert '"prompt_cache_key_enabled": True' in patched
    assert "preflight_xai_request(" in patched
    assert "record_xai_response(" in patched
    assert "record_xai_failure(" in patched
    assert 'max_output_tokens=2000' in patched
    assert '"prompt_cache_key": "iios-grok-social-v1"' in patched
    assert '"max_tool_calls": 3' in patched
    assert "query_label=subject" in patched
    assert '"exact_cost_usd"' in patched
    assert '"cached_input_tokens"' in patched
    assert '"trade_execution_permission": False' in patched
    assert '"capital_authority": False' in patched
    assert '"live_execution": False' in patched


def test_sdk_adapter_does_not_bypass_binding_governor():
    spec = importlib.util.spec_from_file_location("grok_xai_sdk_adapter", ADAPTER)
    assert spec and spec.loader
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    original = object()
    fake = SimpleNamespace(
        _run_x_search=original,
        grok_plan=lambda: {"cost_governor_binding": True},
    )
    adapter.install_xai_sdk_x_search(fake)
    assert fake._run_x_search is original
    assert fake._xai_official_sdk_adapter_skipped_for_cost_governor is True
    assert fake._xai_official_sdk_adapter_installed is False


def test_sdk_adapter_remains_available_without_binding_governor(monkeypatch):
    spec = importlib.util.spec_from_file_location("grok_xai_sdk_adapter_unbound", ADAPTER)
    assert spec and spec.loader
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)

    original = object()
    fake = SimpleNamespace(
        _run_x_search=original,
        grok_plan=lambda: {"cost_governor_binding": False},
        MAX_X_SEARCH_ATTEMPTS=1,
        grok_timeout_seconds=lambda: 30.0,
        grok_model=lambda: "grok-test",
    )
    adapter.install_xai_sdk_x_search(fake)
    assert fake._run_x_search is not original
    assert fake._xai_official_sdk_adapter_installed is True


def test_no_secret_or_prompt_is_embedded_in_cost_helper():
    helper = (ROOT / "BACK END" / "backend" / "model_cost_enforcement.py").read_text(encoding="utf-8")
    assert "XAI_API_KEY" not in helper
    assert '"query": query' not in helper
    assert '"prompt":' not in helper
    assert "query_fingerprint" in helper
    assert "XAI_COST_IN_USD_TICKS" in helper
    assert '"capital_authority": False' in helper
    assert '"trade_execution_permission": False' in helper
    assert '"live_execution": False' in helper
