from __future__ import annotations

from importlib import import_module
from typing import Any

REGISTRY_VERSION = "grok-router-registry-v1"

# Mount the experiment's HTTP/control surfaces in one governed place. Modules
# without a router are deliberately excluded. Import failures are fatal so the
# backend never pretends the experiment is fully mounted when it is not.
ROUTER_MODULES = (
    "grok_social_intelligence",
    "grok_experiment_manifest",
    "grok_ab_benchmark",
    "grok_ab_reuse",
    "grok_discovery_lead_time",
    "grok_experiment_scorecard",
    "grok_false_positive_tracker",
    "grok_opportunity_discovery",
    "grok_paper_value",
    "grok_shadow_paper",
    "grok_value_cycle",
    "grok_value_cycle_async",
    "grok_value_instrumentation",
    "grok_value_probe",
    "grok_value_scheduler",
    "grok_value_scorecard",
)


def install_grok_routers(app: Any) -> dict[str, Any]:
    if getattr(app.state, "_iios_grok_router_registry_installed", False):
        return {
            "registry_version": REGISTRY_VERSION,
            "installed": True,
            "already_installed": True,
            "modules": list(getattr(app.state, "_iios_grok_router_modules", ())),
        }

    mounted: list[str] = []
    for module_name in ROUTER_MODULES:
        module = import_module(module_name)
        router = getattr(module, "router", None)
        if router is None:
            raise RuntimeError(f"Grok router registry expected {module_name}.router")
        app.include_router(router)
        mounted.append(module_name)

    app.state._iios_grok_router_registry_installed = True
    app.state._iios_grok_router_modules = tuple(mounted)
    return {
        "registry_version": REGISTRY_VERSION,
        "installed": True,
        "already_installed": False,
        "modules": mounted,
        "research_only": True,
        "paper_mode": True,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
