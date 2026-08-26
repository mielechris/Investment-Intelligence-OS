from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_SANDBOX = Path("/tmp/iios-kimi-swarm")
DEFAULT_TIMEOUT_SECONDS = 1800


def _env(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def server_url() -> str:
    return _env("IIOS_KIMI_CODE_SERVER_URL").rstrip("/")


def server_token() -> str:
    return _env("IIOS_KIMI_CODE_SERVER_TOKEN")


def sandbox_path() -> Path:
    value = _env("IIOS_KIMI_CODE_SWARM_CWD")
    path = Path(value).expanduser() if value else DEFAULT_SANDBOX
    path.mkdir(parents=True, exist_ok=True)
    return path


def _valid_local_server(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allow_remote = _env("IIOS_ALLOW_REMOTE_KIMI_CODE_SERVER") in {"1", "true", "TRUE", "yes", "YES"}
    if allow_remote:
        return parsed.scheme in {"http", "https"} and bool(host)
    return parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}


def configuration_status() -> dict[str, Any]:
    url = server_url()
    token = server_token()
    return {
        "configured": bool(url and token),
        "server_url": url or None,
        "local_server_only_by_default": True,
        "server_host_approved": _valid_local_server(url) if url else False,
        "credential_present": bool(token),
        "credential_exposed": False,
        "experimental_server_api": True,
        "native_swarm_mode_supported_by_bridge": True,
        "sandbox_workspace": str(sandbox_path()),
        "repo_write_access_granted": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _call(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    url = server_url()
    token = server_token()
    if not url or not token:
        raise RuntimeError("KIMI_CODE_SWARM_NOT_CONFIGURED")
    if not _valid_local_server(url):
        raise ValueError("Kimi Code server must be local unless IIOS_ALLOW_REMOTE_KIMI_CODE_SERVER=1")

    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"

    request = Request(url + path, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            value = json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:1000]
        except Exception:
            pass
        raise RuntimeError(f"KIMI_CODE_HTTP_{exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"KIMI_CODE_SERVER_ERROR: {type(exc).__name__}: {exc}") from exc

    if not isinstance(value, dict):
        raise ValueError("Kimi Code server returned non-object JSON")
    if value.get("code") not in {0, None}:
        raise RuntimeError(f"KIMI_CODE_BUSINESS_ERROR: {value.get('code')} {value.get('msg')}")
    data = value.get("data")
    return data if isinstance(data, dict) else {"value": data}


def _assistant_text(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        parts = message.get("content") or []
        if isinstance(parts, str) and parts.strip():
            return parts.strip()
        text_parts = []
        for part in parts if isinstance(parts, list) else []:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text") or ""))
        text = "\n".join(x for x in text_parts if x).strip()
        if text:
            return text
    return ""


def run_native_swarm(
    *,
    prompt: str,
    model: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    status = configuration_status()
    if not status["configured"]:
        return {
            "status": "SOURCE_NOT_CONFIGURED",
            "configuration": status,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    meta = _call("GET", "/api/v1/meta", timeout=20)
    session = _call(
        "POST",
        "/api/v1/sessions",
        {
            "metadata": {
                "cwd": str(sandbox_path()),
                "iios_context_only": True,
            },
            "title": "IIOS Kimi Research Swarm",
        },
        timeout=30,
    )
    session_id = str(session.get("id") or "")
    if not session_id:
        raise RuntimeError("KIMI_CODE_SESSION_ID_MISSING")

    agent_config: dict[str, Any] = {
        "permission_mode": "auto",
        "swarm_mode": True,
        "thinking": "high",
    }
    if model:
        agent_config["model"] = model

    _call(
        "POST",
        f"/api/v1/sessions/{session_id}/profile",
        {"agent_config": agent_config},
        timeout=30,
    )
    _call(
        "POST",
        f"/api/v1/sessions/{session_id}/prompts",
        {
            "content": [{"type": "text", "text": prompt}],
            "permission_mode": "auto",
        },
        timeout=30,
    )

    deadline = time.time() + max(60, min(int(timeout_seconds), 7200))
    final_status: dict[str, Any] = {}
    while time.time() < deadline:
        final_status = _call("GET", f"/api/v1/sessions/{session_id}/status", timeout=20)
        if not final_status.get("busy") and final_status.get("last_turn_reason") in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)
    else:
        raise TimeoutError("KIMI_CODE_SWARM_TIMEOUT")

    query = urlencode({"page_size": 100, "role": "assistant"})
    message_page = _call(
        "GET",
        f"/api/v1/sessions/{session_id}/messages?{query}",
        timeout=30,
    )
    messages = message_page.get("items") or []
    text = _assistant_text(messages if isinstance(messages, list) else [])

    snapshot = _call("GET", f"/api/v1/sessions/{session_id}/snapshot", timeout=30)
    usage = ((snapshot.get("session") or {}).get("usage") or {}) if isinstance(snapshot, dict) else {}
    subagents = snapshot.get("subagents") or [] if isinstance(snapshot, dict) else []

    return {
        "status": "CAPTURED" if final_status.get("last_turn_reason") == "completed" else "FAILED",
        "session_id": session_id,
        "output_text": text,
        "subagent_count": len(subagents) if isinstance(subagents, list) else 0,
        "usage": usage,
        "server_meta": {
            "version": meta.get("version"),
        },
        "configuration": status,
        "repo_write_access_granted": False,
        "context_only": True,
        "qualification_evidence": False,
        "gap_resolution_eligible": False,
        "capital_authority": False,
        "trade_signal": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
