from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVATOR = ROOT / "scripts" / "activate_batch10m_grok_cost_enforcement_v2.py"
REGISTRY = ROOT / "BACK END" / "backend" / "grok_router_registry.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_contains_required_grok_surfaces():
    registry = _load(REGISTRY, "grok_router_registry_test")
    required = set(registry.REQUIRED_ROUTER_MODULES)
    assert {
        "grok_social_intelligence",
        "grok_experiment_manifest",
        "grok_opportunity_discovery",
        "grok_value_probe",
        "grok_value_cycle",
        "grok_value_cycle_async",
        "grok_value_scheduler",
    }.issubset(required)


def test_registry_does_not_require_helper_modules_to_export_routers():
    registry = _load(REGISTRY, "grok_router_registry_helpers_test")
    required = set(registry.REQUIRED_ROUTER_MODULES)
    optional = set(registry.OPTIONAL_ROUTER_MODULES)
    assert registry.REGISTRY_VERSION == "grok-router-registry-v2"
    assert "grok_value_instrumentation" not in required
    assert "grok_value_instrumentation" in optional
    text = REGISTRY.read_text(encoding="utf-8")
    assert "non_router_modules.append(module_name)" in text
    assert "Required Grok HTTP surface is missing" in text


def test_app_patch_is_idempotent_and_exactly_once():
    activator = _load(ACTIVATOR, "grok_cost_activator_v2_test")
    source = (
        "from governed_paper_execution_api import router as governed_paper_execution_router\n"
        "app.include_router(semiconductor_router)\n"
        "app.version = '0.13.5'\n"
    )
    patched = activator.patch_app(source)
    assert patched.count("from grok_router_registry import install_grok_routers") == 1
    assert patched.count("install_grok_routers(app)") == 1
    patched_again = activator.patch_app(patched)
    assert patched_again == patched


def test_router_activation_has_no_authority_escalation_markers():
    text = ACTIVATOR.read_text(encoding="utf-8") + REGISTRY.read_text(encoding="utf-8")
    assert '"capital_authority": False' in text
    assert '"trade_execution_permission": False' in text
    assert '"live_execution": False' in text
    assert "backend_restart_performed" in text
