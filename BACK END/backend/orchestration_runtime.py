from __future__ import annotations

import hashlib
import os
import threading
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter


router = APIRouter()

DEFAULT_MODEL = "gpt-5.6-luna"
BASELINE_PROFILE = "baseline"
SPEED_TRIAL_PROFILE = "speed_trial"
ALLOWED_PROFILES = {BASELINE_PROFILE, SPEED_TRIAL_PROFILE}
ALLOWED_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
DEFAULT_FIRST_WAVE_TIMEOUT_SECONDS = 45.0
DEFAULT_CRITICAL_TIMEOUT_SECONDS = 60.0
DEFAULT_COMMITTEE_TIMEOUT_SECONDS = 60.0
MIN_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 90.0

_context = threading.local()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def selected_profile() -> str:
    value = str(os.getenv("IIOS_ORCHESTRATION_PROFILE", BASELINE_PROFILE)).strip().lower()
    return value if value in ALLOWED_PROFILES else BASELINE_PROFILE


def _effort_env(name: str, default: str) -> str:
    value = str(os.getenv(name, default)).strip().lower()
    return value if value in ALLOWED_EFFORTS else default


def _model_env(name: str, default: str = DEFAULT_MODEL) -> str:
    value = str(os.getenv(name, default)).strip()
    return value or default


def _timeout_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(MIN_TIMEOUT_SECONDS, min(value, MAX_TIMEOUT_SECONDS))


def runtime_policy() -> dict[str, Any]:
    profile = selected_profile()
    first_wave_default = "low" if profile == SPEED_TRIAL_PROFILE else "medium"

    return {
        "profile": profile,
        "first_wave_model": _model_env("IIOS_FIRST_WAVE_MODEL"),
        "critical_model": _model_env("IIOS_CRITICAL_MODEL"),
        "committee_model": _model_env("IIOS_COMMITTEE_MODEL"),
        "first_wave_reasoning_effort": _effort_env(
            "IIOS_FIRST_WAVE_REASONING_EFFORT",
            first_wave_default,
        ),
        "critical_reasoning_effort": _effort_env(
            "IIOS_CRITICAL_REASONING_EFFORT",
            "medium",
        ),
        "committee_reasoning_effort": _effort_env(
            "IIOS_COMMITTEE_REASONING_EFFORT",
            "medium",
        ),
        "first_wave_timeout_seconds": _timeout_env(
            "IIOS_FIRST_WAVE_TIMEOUT_SECONDS",
            DEFAULT_FIRST_WAVE_TIMEOUT_SECONDS,
        ),
        "critical_timeout_seconds": _timeout_env(
            "IIOS_CRITICAL_TIMEOUT_SECONDS",
            DEFAULT_CRITICAL_TIMEOUT_SECONDS,
        ),
        "committee_timeout_seconds": _timeout_env(
            "IIOS_COMMITTEE_TIMEOUT_SECONDS",
            DEFAULT_COMMITTEE_TIMEOUT_SECONDS,
        ),
        "prompt_cache_enabled": _bool_env("IIOS_PROMPT_CACHE_ENABLED", True),
        "prompt_cache_ttl": "30m",
        "judgment_output_cache": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _exact_prompt_cache_key(role: str, model: str, input_value: Any) -> str | None:
    if not isinstance(input_value, str) or not input_value:
        return None
    digest = hashlib.sha256(
        f"{role}\0{model}\0{input_value}".encode("utf-8")
    ).hexdigest()
    return f"iios-{digest[:48]}"


@contextmanager
def _request_context(
    *,
    role: str,
    model: str,
    effort: str,
    cache_enabled: bool,
    timeout_seconds: float | None = None,
):
    previous = getattr(_context, "request", None)
    _context.request = {
        "role": role,
        "model": model,
        "effort": effort,
        "cache_enabled": cache_enabled,
        "timeout_seconds": timeout_seconds,
    }
    try:
        yield
    finally:
        _context.request = previous


class _RoutedResponses:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *args, **kwargs):
        request = getattr(_context, "request", None)
        if request:
            kwargs["model"] = request["model"]
            reasoning = dict(kwargs.get("reasoning") or {})
            reasoning["effort"] = request["effort"]
            kwargs["reasoning"] = reasoning

            timeout_seconds = request.get("timeout_seconds")
            if timeout_seconds:
                kwargs.setdefault("timeout", float(timeout_seconds))

            if request.get("cache_enabled"):
                cache_key = _exact_prompt_cache_key(
                    str(request["role"]),
                    str(request["model"]),
                    kwargs.get("input"),
                )
                if cache_key:
                    kwargs.setdefault("prompt_cache_key", cache_key)
                    kwargs.setdefault("prompt_cache_options", {"ttl": "30m"})

        return self._inner.create(*args, **kwargs)


def _routed_openai_factory(original_openai):
    class RoutedOpenAI:
        def __init__(self, *args, **kwargs):
            self._inner = original_openai(*args, **kwargs)
            self.responses = _RoutedResponses(self._inner.responses)

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

    return RoutedOpenAI


def install_orchestration_runtime(module) -> None:
    """Install thread-safe model/effort routing, deadlines, and prompt caching.

    Baseline preserves Luna + medium reasoning. The optional speed_trial changes
    only the six first-wave desks to low reasoning. Request deadlines are bounded
    and role-specific. Prompt caching only reuses prompt processing; prior agent
    judgments are never reused as outputs.
    """
    if getattr(module, "_runtime_layer_installed", False):
        return

    module._runtime_layer_installed = True

    original_openai = module.OpenAI
    routed_openai = _routed_openai_factory(original_openai)

    module.run_specialist.__globals__["OpenAI"] = routed_openai
    module.OpenAI = routed_openai

    original_run_specialist = module.run_specialist
    original_synthesize = module._synthesize_committee

    def routed_run_specialist(agent_key: str, topic: str, evidence=None):
        policy = runtime_policy()
        critical = agent_key in set(module.SECOND_WAVE)
        model = policy["critical_model"] if critical else policy["first_wave_model"]
        effort = (
            policy["critical_reasoning_effort"]
            if critical
            else policy["first_wave_reasoning_effort"]
        )
        timeout_seconds = (
            policy["critical_timeout_seconds"]
            if critical
            else policy["first_wave_timeout_seconds"]
        )
        with _request_context(
            role=agent_key,
            model=model,
            effort=effort,
            cache_enabled=bool(policy["prompt_cache_enabled"]),
            timeout_seconds=timeout_seconds,
        ):
            result = original_run_specialist(agent_key, topic, evidence)
        return {
            **result,
            "runtime_profile": policy["profile"],
            "model_used": model,
            "reasoning_effort": effort,
            "request_timeout_seconds": timeout_seconds,
            "prompt_cache_enabled": bool(policy["prompt_cache_enabled"]),
        }

    def routed_synthesize(*args, **kwargs):
        policy = runtime_policy()
        with _request_context(
            role="committee",
            model=policy["committee_model"],
            effort=policy["committee_reasoning_effort"],
            cache_enabled=bool(policy["prompt_cache_enabled"]),
            timeout_seconds=policy["committee_timeout_seconds"],
        ):
            result = original_synthesize(*args, **kwargs)
        return {
            **result,
            "runtime_profile": policy["profile"],
            "committee_model_used": policy["committee_model"],
            "committee_reasoning_effort": policy["committee_reasoning_effort"],
            "committee_timeout_seconds": policy["committee_timeout_seconds"],
            "prompt_cache_enabled": bool(policy["prompt_cache_enabled"]),
        }

    module.run_specialist = routed_run_specialist
    module._synthesize_committee = routed_synthesize


@router.get("/orchestration-runtime/plan")
def orchestration_runtime_plan():
    return runtime_policy()
