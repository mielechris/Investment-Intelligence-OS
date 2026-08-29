from __future__ import annotations

from importlib import import_module
from typing import Any

REGISTRY_VERSION = "grok-router-registry-v2"

# These surfaces are required for governed Grok operation and must expose
# FastAPI routers. If any of them is missing a router, backend startup fails
# closed instead of pretending Grok is mounted.
REQUIRED_ROUTER_MODULES = (
    "grok_social_intelligence",
    "grok_experiment_manifest",
    "grok_opportunity_discovery",
    "grok_value_probe",
    "grok_value_cycle",
    "grok_value_cycle_async",
    "grok_value_scheduler",
)

# These experiment modules may expose HTTP routes, but some are deliberately
# helper/measurement libraries. Import them so import failures remain visible,
# mount them only when a real FastAPI `router` exists, and record explicit
# non-router skips rather than raising on valid helper modules.
OPTIONAL_ROUTER_MODULES = (
    "grok_ab_benchmark",
    "grok_ab_reuse",
    "grok_discovery_lead_time",
    "grok_experiment_scorecard",
    "grok_false_positive_tracker",
    "grok_paper_value",
    "grok_shadow_paper",
    "grok_value_instrumentation",
    "grok_value_scorecard",
)

ROUTER_MODULES = REQUIRED_ROUTER_MODULES + OPTIONAL_ROUTER_MODULES


def install_grok_routers(app: Any) -> dict[str, Any]:
    if getattr(app.state, "_iios_grok_router_registry_installed", False):
        return {
            "registry_version": REGISTRY_VERSION,
            "installed": True,
            "already_installed": True,
            "modules": list(getattr(app.state, "_iios_grok_router_modules", ())),
            "non_router_modules": list(getattr(app.state, "_iios_grok_non_router_modules", ())),
        }

    mounted: list[str] = []
    non_router_modules: list[str] = []

    for module_name in REQUIRED_ROUTER_MODULES:
        module = import_module(module_name)
        router = getattr(module, "router", None)
        if router is None:
            raise RuntimeError(f"Required Grok HTTP surface is missing {module_name}.router")
        app.include_router(router)
        mounted.append(module_name)

    for module_name in OPTIONAL_ROUTER_MODULES:
        module = import_module(module_name)
        router = getattr(module, "router", None)
        if router is None:
            non_router_modules.append(module_name)
            continue
        app.include_router(router)
        mounted.append(module_name)

    app.state._iios_grok_router_registry_installed = True
    app.state._iios_grok_router_modules = tuple(mounted)
    app.state._iios_grok_non_router_modules = tuple(non_router_modules)
    return {
        "registry_version": REGISTRY_VERSION,
        "installed": True,
        "already_installed": False,
        "modules": mounted,
        "non_router_modules": non_router_modules,
        "research_only": True,
        "paper_mode": True,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
