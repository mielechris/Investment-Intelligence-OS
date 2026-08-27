from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_FLASH_MODEL = "gemini-3.7-flash"
DEFAULT_PRO_MODEL = "gemini-3.1-pro-preview"
DEFAULT_TIMEOUT_SECONDS = 180
APPROVED_HOSTS = {"generativelanguage.googleapis.com"}
JSON_RESPONSE_MIME_ENUM = "APPLICATION_JSON"


def _env(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def api_key() -> str:
    return _env("IIOS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


def base_url() -> str:
    return _env("IIOS_GEMINI_BASE_URL") or DEFAULT_BASE_URL


def flash_model() -> str:
    return _env("IIOS_GEMINI_FLASH_MODEL") or DEFAULT_FLASH_MODEL


def pro_model() -> str:
    return _env("IIOS_GEMINI_PRO_MODEL") or DEFAULT_PRO_MODEL


def _host(value: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(value).hostname or "").lower()


def validate_base_url(value: str) -> None:
    host = _host(value)
    allow_custom = _env("IIOS_ALLOW_CUSTOM_GEMINI_HOST") in {"1", "true", "TRUE", "yes", "YES"}
    if allow_custom:
        return
    if host not in APPROVED_HOSTS:
        raise ValueError(
            f"Gemini base URL host {host or '<missing>'} is not approved. "
            "Set IIOS_ALLOW_CUSTOM_GEMINI_HOST=1 only for a separately governed gateway."
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
        "flash_model": flash_model(),
        "pro_model": pro_model(),
        "google_search_grounding": True,
        "url_context": True,
        "structured_outputs": True,
        "thinking_levels": True,
        "context_only": True,
        "qualification_evidence": False,
        "capital_authority": False,
        "trade_signal": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _quota_or_billing_blocked(detail: str) -> bool:
    text = str(detail or "").lower()
    return any(
        marker in text
        for marker in (
            "exceeded your current quota",
            "check your plan and billing details",
            "resource_exhausted",
            "quota exceeded",
            "billing",
        )
    )


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
        raise RuntimeError("GEMINI_PROVIDER_NOT_CONFIGURED")

    root = base_url().rstrip("/")
    validate_base_url(root)
    url = root + path
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "x-goog-api-key": key,
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
                    raise ValueError("Gemini API returned non-object JSON")
                return value
        except HTTPError as exc:
            last_error = exc
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:1500]
            except Exception:
                pass
            if exc.code == 429 and _quota_or_billing_blocked(detail):
                raise RuntimeError(
                    "GEMINI_QUOTA_OR_BILLING_BLOCKED: current project quota/billing tier does not permit this request"
                ) from exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= retries:
                raise RuntimeError(f"GEMINI_HTTP_{exc.code}: {detail}") from exc
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else 1.5 * (2**attempt)
            except (TypeError, ValueError):
                delay = 1.5 * (2**attempt)
            time.sleep(min(max(delay, 1.0), 8.0))
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"GEMINI_PROVIDER_ERROR: {type(exc).__name__}: {exc}") from exc
            time.sleep(min(1.0 * (2**attempt), 4.0))

    raise RuntimeError(f"GEMINI_PROVIDER_ERROR: {last_error}")


def _response_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        raise ValueError("Gemini response missing candidates")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_parts: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    text = "\n".join(x for x in text_parts if x).strip()
    if not text:
        raise ValueError("Gemini response missing text")
    return text


def _json_content(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Gemini structured output was not a JSON object")
    return value


def _grounding(response: dict[str, Any]) -> dict[str, Any]:
    candidates = response.get("candidates") or []
    candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    grounding = candidate.get("groundingMetadata") or candidate.get("grounding_metadata") or {}
    url_context = candidate.get("urlContextMetadata") or candidate.get("url_context_metadata") or {}
    queries = grounding.get("webSearchQueries") or grounding.get("web_search_queries") or []
    chunks = grounding.get("groundingChunks") or grounding.get("grounding_chunks") or []
    sources: list[dict[str, Any]] = []
    for chunk in chunks if isinstance(chunks, list) else []:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web") or {}
        if not isinstance(web, dict):
            continue
        uri = str(web.get("uri") or "").strip()
        title = str(web.get("title") or "").strip()
        if uri or title:
            sources.append({"title": title or None, "uri": uri or None})
    return {
        "web_search_queries": [str(x) for x in queries if str(x).strip()][:30],
        "grounding_sources": sources[:50],
        "url_context_metadata": url_context if isinstance(url_context, dict) else {},
    }


def research_json(
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    model: str | None = None,
    thinking_level: str = "medium",
    use_google_search: bool = True,
    use_url_context: bool = True,
    max_output_tokens: int = 8000,
) -> dict[str, Any]:
    selected_model = model or flash_model()
    prompt = f"SYSTEM INSTRUCTION:\n{system}\n\nRESEARCH REQUEST:\n{user}"
    tools: list[dict[str, Any]] = []
    if use_google_search:
        tools.append({"google_search": {}})
    if use_url_context:
        tools.append({"url_context": {}})

    level = thinking_level if thinking_level in {"low", "medium", "high"} else "medium"
    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": max(512, min(int(max_output_tokens), 32000)),
            "thinkingConfig": {"thinkingLevel": level},
            "responseFormat": {
                "text": {
                    "mimeType": JSON_RESPONSE_MIME_ENUM,
                    "schema": schema,
                }
            },
        },
    }
    if tools:
        payload["tools"] = tools

    started = time.perf_counter()
    response = _request(
        "POST",
        f"/models/{quote(selected_model, safe='-._')}:generateContent",
        payload,
    )
    latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
    text = _response_text(response)
    grounding = _grounding(response)
    return {
        "status": "CAPTURED",
        "model": selected_model,
        "output": _json_content(text),
        "usage": response.get("usageMetadata") or response.get("usage_metadata") or {},
        "latency_ms": latency_ms,
        "provider": "GOOGLE_GEMINI_API",
        "google_search_enabled": bool(use_google_search),
        "url_context_enabled": bool(use_url_context),
        "thinking_level": level,
        **grounding,
        "credential_exposed": False,
        "context_only": True,
        "qualification_evidence": False,
        "capital_authority": False,
        "trade_signal": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def preflight(*, require_research_tools: bool = False) -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    if require_research_tools:
        system = (
            "This is an IIOS provider capability canary. Use Google Search to verify that the Gemini API documentation is publicly "
            "available, then return the requested JSON only. Do not make any investment recommendation."
        )
        user = 'Use Google Search and return {"ok": true}.'
    else:
        system = "Return the requested JSON only. Do not use external tools unless necessary."
        user = 'Return {"ok": true}.'
    result = research_json(
        system=system,
        user=user,
        schema=schema,
        model=flash_model(),
        thinking_level="low",
        use_google_search=require_research_tools,
        use_url_context=require_research_tools,
        max_output_tokens=512,
    )
    if (result.get("output") or {}).get("ok") is not True:
        raise RuntimeError("GEMINI_PREFLIGHT_INVALID_RESPONSE")
    return result
