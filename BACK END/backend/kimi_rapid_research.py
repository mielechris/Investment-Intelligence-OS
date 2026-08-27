from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import kimi_provider


DEFAULT_MAX_TOOL_ROUNDS = max(2, min(int(os.getenv("IIOS_9E_KIMI_TOOL_ROUNDS", "4")), 8))
DEFAULT_MAX_WORKERS = max(1, min(int(os.getenv("IIOS_9E_KIMI_WORKERS", "4")), 8))
DEFAULT_MAX_TOKENS = max(1000, min(int(os.getenv("IIOS_9E_KIMI_MAX_TOKENS", "6000")), 12000))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, number))


def _list(value: Any, limit: int = 15, chars: int = 700) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x)[:chars] for x in value if str(x).strip()][:limit]


def _system_prompt() -> str:
    return (
        "You are Kimi K3 operating as IIOS's rapid pre-case due-diligence research crew. "
        "Use the available web-search tools to verify the catalyst, identify primary or credible sources, "
        "separate fact from inference, test whether the move appears structural or temporary, and list missing evidence. "
        "Do not recommend a trade. Return JSON only with keys: ticker, research_score 0..100, verified_catalysts, "
        "counterevidence, primary_sources_found, open_questions, research_summary, complexity_score 0..100."
    )


def _force_synthesis(messages: list[dict[str, Any]], model: str, tool_calls_used: int) -> dict[str, Any]:
    final_messages = list(messages)
    final_messages.append(
        {
            "role": "user",
            "content": (
                "Stop calling tools. Using only the evidence already collected in this conversation, synthesize the final "
                "answer now. Return one valid JSON object with exactly these keys: ticker, research_score, verified_catalysts, "
                "counterevidence, primary_sources_found, open_questions, research_summary, complexity_score."
            ),
        }
    )
    payload: dict[str, Any] = {
        "model": model,
        "messages": final_messages,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": DEFAULT_MAX_TOKENS,
    }
    if model.startswith("kimi-k3"):
        payload["reasoning_effort"] = "high"
    elif model.startswith("kimi-k2.6"):
        payload["thinking"] = {"type": "enabled"}

    response = kimi_provider._request("POST", "/chat/completions", payload)
    text = kimi_provider._message_content(response)
    return {
        "status": "CAPTURED",
        "model": response.get("model") or model,
        "output": kimi_provider._json_content(text),
        "usage": response.get("usage") or {},
        "provider_request_id": response.get("id"),
        "provider": "KIMI_OPEN_PLATFORM_FORMULA_WEB_SEARCH_FORCED_SYNTHESIS",
        "tool_calls_used": tool_calls_used,
        "forced_synthesis": True,
    }


def research_one(row: dict[str, Any], *, max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    model = kimi_provider.resolve_model()
    tools = kimi_provider._formula_tools(kimi_provider.WEB_SEARCH_FORMULA)
    if not tools:
        raise RuntimeError("KIMI_WEB_SEARCH_TOOLS_UNAVAILABLE")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": json.dumps(row, ensure_ascii=False, default=str)},
    ]
    tool_calls_used = 0
    rounds_used = 0

    for _ in range(max(1, min(int(max_tool_rounds), 8))):
        rounds_used += 1
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "max_completion_tokens": DEFAULT_MAX_TOKENS,
        }
        if model.startswith("kimi-k3"):
            payload["reasoning_effort"] = "high"
        elif model.startswith("kimi-k2.6"):
            payload["thinking"] = {"type": "enabled"}

        response = kimi_provider._request("POST", "/chat/completions", payload)
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("Kimi web research response missing choices")
        message = (choices[0] or {}).get("message") or {}
        calls = message.get("tool_calls") or []

        if not calls:
            content = str(message.get("content") or "")
            value = kimi_provider._json_content(content)
            return {
                "ticker": ticker,
                "status": "CAPTURED",
                "model": response.get("model") or model,
                "output": value,
                "usage": response.get("usage") or {},
                "provider_request_id": response.get("id"),
                "provider": "KIMI_OPEN_PLATFORM_FORMULA_WEB_SEARCH",
                "tool_calls_used": tool_calls_used,
                "tool_rounds_used": rounds_used,
                "forced_synthesis": False,
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
            result = kimi_provider._formula_fiber(kimi_provider.WEB_SEARCH_FORMULA, function)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": result,
                }
            )
            tool_calls_used += 1

    final = _force_synthesis(messages, model, tool_calls_used)
    final["ticker"] = ticker
    final["tool_rounds_used"] = rounds_used
    return final


def normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("output") or {}
    if not isinstance(value, dict):
        raise ValueError("Kimi research output is not a JSON object")
    ticker = str(value.get("ticker") or result.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("Kimi research output missing ticker")
    return {
        "research_score": _safe_float(value.get("research_score")),
        "verified_catalysts": _list(value.get("verified_catalysts")),
        "counterevidence": _list(value.get("counterevidence")),
        "primary_sources_found": _list(value.get("primary_sources_found")),
        "open_questions": _list(value.get("open_questions")),
        "research_summary": str(value.get("research_summary") or "")[:3500],
        "complexity_score": _safe_float(value.get("complexity_score")),
        "provider_model": result.get("model"),
        "usage": result.get("usage") or {},
        "tool_calls_used": int(result.get("tool_calls_used") or 0),
        "tool_rounds_used": int(result.get("tool_rounds_used") or 0),
        "forced_synthesis": result.get("forced_synthesis") is True,
        "context_only": True,
    }


def run_kimi_rapid_research(
    rows: list[dict[str, Any]],
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    output: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    if not rows:
        return output, errors

    with ThreadPoolExecutor(max_workers=min(max(1, int(max_workers)), len(rows))) as pool:
        future_map = {
            pool.submit(research_one, row, max_tool_rounds=max_tool_rounds): str(row.get("ticker") or "").upper()
            for row in rows
        }
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                result = future.result()
                normalized = normalize_result(result)
                resolved = str(result.get("ticker") or ticker).upper()
                output[resolved] = normalized
            except Exception as exc:  # noqa: BLE001
                errors[ticker or "UNKNOWN"] = f"{type(exc).__name__}: {exc}"[:2000]

    return output, errors
