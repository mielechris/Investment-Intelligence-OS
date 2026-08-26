from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k3"
DEFAULT_TIMEOUT_SECONDS = 180
WEB_SEARCH_FORMULA = "moonshot/web-search:latest"
APPROVED_HOSTS = {
    "api.moonshot.cn",
    "api.moonshot.ai",
    "api.kimi.com",
}


def _env(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def api_key() -> str:
    return _env("IIOS_KIMI_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY")


def base_url() -> str:
    return _env("IIOS_KIMI_BASE_URL", "MOONSHOT_BASE_URL") or DEFAULT_BASE_URL


def preferred_model() -> str:
    return _env("IIOS_KIMI_MODEL") or DEFAULT_MODEL


def _host(value: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(value).hostname or "").lower()


def validate_base_url(value: str) -> None:
    host = _host(value)
    allow_custom = _env("IIOS_ALLOW_CUSTOM_KIMI_HOST") in {"1", "true", "TRUE", "yes", "YES"}
    if allow_custom:
        return
    if host not in APPROVED_HOSTS:
        raise ValueError(
            f"Kimi base URL host {host or '<missing>'} is not approved. "
            "Set IIOS_ALLOW_CUSTOM_KIMI_HOST=1 only for a separately governed gateway."
        )


def configuration_status() -> dict[str, Any]:
    key = api_key()
    url = base_url().rstrip("/")
    return {
        "configured": bool(key),
        "credential_present": bool(key),
        "credential_exposed": False,
        "base_url": url,
        "base_url_host": _host(url),
        "model_preference": preferred_model(),
        "openai_compatible_chat_completions": True,
        "json_mode": True,
        "formula_web_search_supported": True,
        "k3_long_context_supported_by_provider": True,
        "consumer_deep_research_api_available": False,
        "deep_research_via_k3_orchestration": True,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 2,
) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise RuntimeError("KIMI_PROVIDER_NOT_CONFIGURED")

    root = base_url().rstrip("/")
    validate_base_url(root)
    url = root + path
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                value = json.loads(raw) if raw else {}
                if not isinstance(value, dict):
                    raise ValueError("Kimi API returned non-object JSON")
                return value
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8")[:1000]
                except Exception:
                    pass
                raise RuntimeError(f"KIMI_HTTP_{exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"KIMI_PROVIDER_ERROR: {type(exc).__name__}: {exc}") from exc
        time.sleep(2**attempt)

    raise RuntimeError(f"KIMI_PROVIDER_ERROR: {last_error}")


def list_models() -> list[str]:
    response = _request("GET", "/models", timeout=30, retries=1)
    rows = response.get("data") or []
    models = []
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            models.append(str(row["id"]))
    return models


def resolve_model() -> str:
    wanted = preferred_model()
    if not api_key():
        return wanted
    try:
        available = set(list_models())
    except Exception:
        return wanted
    for candidate in (wanted, "kimi-k3", "kimi-k2.6"):
        if candidate in available:
            return candidate
    return wanted


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise ValueError("Kimi response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text.append(str(part.get("text") or ""))
        return "\n".join(text)
    return str(content or "")


def _json_content(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Kimi JSON output was not an object")
    return value


def chat_json(
    *,
    system: str,
    user: str,
    max_completion_tokens: int = 6000,
    reasoning_effort: str = "high",
) -> dict[str, Any]:
    model = resolve_model()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max(256, min(int(max_completion_tokens), 32768)),
    }
    if model.startswith("kimi-k3"):
        payload["reasoning_effort"] = reasoning_effort if reasoning_effort in {"low", "high", "max"} else "high"
    elif model.startswith("kimi-k2.6"):
        payload["thinking"] = {"type": "enabled"}

    response = _request("POST", "/chat/completions", payload)
    text = _message_content(response)
    return {
        "status": "CAPTURED",
        "model": response.get("model") or model,
        "output": _json_content(text),
        "usage": response.get("usage") or {},
        "provider_request_id": response.get("id"),
        "provider": "KIMI_OPEN_PLATFORM",
        "credential_exposed": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _formula_tools(uri: str) -> list[dict[str, Any]]:
    response = _request("GET", f"/formulas/{quote(uri, safe=':/')}/tools", timeout=60, retries=1)
    tools = response.get("tools") or []
    return [row for row in tools if isinstance(row, dict)]


def _formula_fiber(uri: str, function: dict[str, Any]) -> str:
    response = _request(
        "POST",
        f"/formulas/{quote(uri, safe=':/')}/fibers",
        {
            "name": function.get("name"),
            "arguments": function.get("arguments"),
        },
        timeout=120,
        retries=1,
    )
    context = response.get("context") or {}
    return str(context.get("output") or context.get("encrypted_output") or "")


def research_json_with_web_search(
    *,
    system: str,
    user: str,
    max_tool_rounds: int = 6,
    max_completion_tokens: int = 6000,
) -> dict[str, Any]:
    model = resolve_model()
    tools = _formula_tools(WEB_SEARCH_FORMULA)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    tool_calls_used = 0

    for _ in range(max(1, min(int(max_tool_rounds), 10))):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "max_completion_tokens": max(256, min(int(max_completion_tokens), 32768)),
        }
        if model.startswith("kimi-k3"):
            payload["reasoning_effort"] = "high"
        response = _request("POST", "/chat/completions", payload)
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("Kimi web research response missing choices")
        message = (choices[0] or {}).get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls:
            content = str(message.get("content") or "")
            return {
                "status": "CAPTURED",
                "model": response.get("model") or model,
                "output": _json_content(content),
                "usage": response.get("usage") or {},
                "provider_request_id": response.get("id"),
                "provider": "KIMI_OPEN_PLATFORM_FORMULA_WEB_SEARCH",
                "tool_calls_used": tool_calls_used,
                "credential_exposed": False,
                "trade_execution_permission": False,
                "live_execution": False,
            }

        messages.append(
            {
                key: value
                for key, value in message.items()
                if key in {"role", "content", "tool_calls"}
            }
        )
        for call in calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function") or {}
            result = _formula_fiber(WEB_SEARCH_FORMULA, function)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": result,
                }
            )
            tool_calls_used += 1

    raise RuntimeError("KIMI_WEB_RESEARCH_TOOL_ROUND_LIMIT")
