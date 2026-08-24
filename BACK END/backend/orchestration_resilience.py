from __future__ import annotations

import threading
import time
from typing import Any, Callable

from fastapi import APIRouter


router = APIRouter()

MAX_TRANSIENT_ATTEMPTS = 2
BREAKER_FAILURE_THRESHOLD = 4
BREAKER_COOLDOWN_SECONDS = 30.0
RETRY_BASE_SECONDS = 0.25

_LOCK = threading.Lock()
_BREAKER = {
    "failure_count": 0,
    "opened_at": None,
    "last_error": None,
}

_TRANSIENT_TOKENS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "rate limit",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "service unavailable",
)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(token in text for token in _TRANSIENT_TOKENS)


def _breaker_snapshot(now: float | None = None) -> dict[str, Any]:
    now = time.monotonic() if now is None else now
    with _LOCK:
        opened_at = _BREAKER["opened_at"]
        if opened_at is not None and now - float(opened_at) >= BREAKER_COOLDOWN_SECONDS:
            _BREAKER["failure_count"] = 0
            _BREAKER["opened_at"] = None
            _BREAKER["last_error"] = None
            opened_at = None
        return {
            "failure_count": int(_BREAKER["failure_count"]),
            "open": opened_at is not None,
            "cooldown_seconds": BREAKER_COOLDOWN_SECONDS,
            "last_error": _BREAKER["last_error"],
        }


def _record_success() -> None:
    with _LOCK:
        _BREAKER["failure_count"] = 0
        _BREAKER["opened_at"] = None
        _BREAKER["last_error"] = None


def _record_transient_failure(exc: Exception) -> None:
    with _LOCK:
        _BREAKER["failure_count"] = int(_BREAKER["failure_count"]) + 1
        _BREAKER["last_error"] = f"{type(exc).__name__}: {exc}"
        if int(_BREAKER["failure_count"]) >= BREAKER_FAILURE_THRESHOLD:
            _BREAKER["opened_at"] = time.monotonic()


def reset_circuit_breaker() -> None:
    _record_success()


def call_with_resilience(call: Callable[[], Any], *, role: str) -> tuple[Any, int]:
    if _breaker_snapshot()["open"]:
        raise RuntimeError(f"ORCHESTRATION_CIRCUIT_OPEN:{role}")

    last_error: Exception | None = None
    for attempt in range(1, MAX_TRANSIENT_ATTEMPTS + 1):
        try:
            result = call()
            _record_success()
            return result, attempt
        except Exception as exc:
            last_error = exc
            if not _is_transient(exc):
                raise
            _record_transient_failure(exc)
            if attempt >= MAX_TRANSIENT_ATTEMPTS or _breaker_snapshot()["open"]:
                raise
            time.sleep(RETRY_BASE_SECONDS * attempt)

    if last_error:
        raise last_error
    raise RuntimeError("Orchestration resilience call exited without result")


class _ResilientResponses:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *args, **kwargs):
        result, _ = call_with_resilience(
            lambda: self._inner.create(*args, **kwargs),
            role="committee_api",
        )
        return result


def _resilient_openai_factory(inner_openai):
    class ResilientOpenAI:
        def __init__(self, *args, **kwargs):
            self._inner = inner_openai(*args, **kwargs)
            self.responses = _ResilientResponses(self._inner.responses)

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

    return ResilientOpenAI


def install_orchestration_resilience(module) -> None:
    """Install bounded retries and a shared fail-closed circuit breaker.

    The layer retries transient model/API failures once. Persistent failures bubble
    into the existing agent error result / committee fail-closed guard. It does not
    alter dispositions, evidence, sizing, authorization, orders, or execution.
    """
    if getattr(module, "_resilience_layer_installed", False):
        return

    module._resilience_layer_installed = True

    original_run_specialist = module.run_specialist

    def resilient_run_specialist(agent_key: str, topic: str, evidence=None):
        result, attempts = call_with_resilience(
            lambda: original_run_specialist(agent_key, topic, evidence),
            role=agent_key,
        )
        return {
            **result,
            "resilience_attempts": attempts,
            "resilience_enabled": True,
        }

    module.run_specialist = resilient_run_specialist

    # Committee synthesis resolves OpenAI from the orchestrator module's global
    # namespace at call time, so this wraps committee API calls without touching
    # the main.py specialist API client used outside this orchestrator.
    module.OpenAI = _resilient_openai_factory(module.OpenAI)


@router.get("/orchestration-resilience/plan")
def resilience_plan():
    return {
        "max_transient_attempts": MAX_TRANSIENT_ATTEMPTS,
        "breaker_failure_threshold": BREAKER_FAILURE_THRESHOLD,
        "breaker_cooldown_seconds": BREAKER_COOLDOWN_SECONDS,
        "retry_base_seconds": RETRY_BASE_SECONDS,
        "fail_closed": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


@router.get("/orchestration-resilience/status")
def resilience_status():
    return {
        "circuit_breaker": _breaker_snapshot(),
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
