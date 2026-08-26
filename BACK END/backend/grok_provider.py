from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://api.x.ai/v1"
DEFAULT_MODEL = "grok-4.6"
DEFAULT_TIMEOUT_SECONDS = 180
APPROVED_HOSTS = {"api.x.ai"}


def _env(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def api_key() -> str:
    return _env("IIOS_GROK_API_KEY", "XAI_API_KEY")


def base_url() -> str:
    return _env("IIOS_GROK_BASE_URL", "XAI_BASE_URL") or DEFAULT_BASE_URL


def preferred_model() -> str:
    return _env("IIOS_GROK_MODEL") or DEFAULT_MODEL


def _host(value: str) -> str:
    return (urlparse(value).hostname or "").lower()


def validate_base_url(value: str) -> None:
    host = _host(value)
    allow_custom = _env("IIOS_ALLOW_CUSTOM_GROK_HOST") in {"1", "true", "TRUE", "yes", "YES"}
    if allow_custom:
        return
    if host not in APPROVED_HOSTS:
        raise ValueError(
            f"Grok base URL host {host or '<missing>'} is not approved. "
            "Set IIOS_ALLOW_CUSTOM_GROK_HOST=1 only for a separately governed gateway."
        )


def configuration_status() -> dict[str, Any]:
    key = api_key()
    root = base_url().rstrip("/")
    return {
        "configured": bool(key),
        "credential_present": bool(key),
        "credential_exposed": False,
        "base_url": root,
        "base_url_host": _host(root),
        "model_preference": preferred_model(),
        "responses_api": True,
        "web_search_supported": True,
        "x_search_supported": True,
        "realtime_requires_search_tools": True,
        "provider_response_storage_requested": False,
        "context_only_default": True,
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
        raise RuntimeError("GROK_PROVIDER_NOT_CONFIGURED")

    root = base_url().rstrip("/")
    validate_base_url(root)
    url = root + path
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    last: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                value = json.loads(raw) if raw else {}
                if not isinstance(value, dict):
                    raise ValueError("Grok API returned non-object JSON")
                return value
        except HTTPError as exc:
            last = exc
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:1000]
            except Exception:
                pass
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise RuntimeError(f"GROK_HTTP_{exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last = exc
            if attempt >= retries:
                raise RuntimeError(f"GROK_PROVIDER_ERROR: {type(exc).__name__}: {exc}") from exc
        time.sleep(2**attempt)
    raise RuntimeError(f"GROK_PROVIDER_ERROR: {last}")


def _output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return str(response.get("output_text") or "")
    parts: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "\n".join(parts)


def _collect_urls(value: Any, output: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"url", "source_url"} and isinstance(item, str) and item.startswith(("http://", "https://")):
                output.append(item)
            else:
                _collect_urls(item, output)
    elif isinstance(value, list):
        for item in value:
            _collect_urls(item, output)


def _citations(response: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    _collect_urls(response.get("output") or [], urls)
    return list(dict.fromkeys(urls))[:100]


def _json_object(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValueError("Grok response did not include text output")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Grok JSON output was not an object")
    return value


def research_json(
    *,
    system: str,
    user: str,
    use_x_search: bool = True,
    use_web_search: bool = True,
) -> dict[str, Any]:
    model = preferred_model()
    tools: list[dict[str, Any]] = []
    if use_web_search:
        tools.append({"type": "web_search"})
    if use_x_search:
        tools.append({"type": "x_search"})

    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "store": False,
    }
    if tools:
        payload["tools"] = tools

    started = time.perf_counter()
    response = _request("POST", "/responses", payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    text = _output_text(response)
    return {
        "status": "CAPTURED",
        "provider": "XAI_GROK_RESPONSES",
        "model": response.get("model") or model,
        "output": _json_object(text),
        "citations": _citations(response),
        "usage": response.get("usage") or {},
        "provider_request_id": response.get("id"),
        "latency_ms": latency_ms,
        "x_search_enabled": use_x_search,
        "web_search_enabled": use_web_search,
        "credential_exposed": False,
        "context_only": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
