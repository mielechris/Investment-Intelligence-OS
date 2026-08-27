from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import gemini_provider


DEFAULT_FINALIST_COUNT = max(4, min(int(os.getenv("IIOS_9E_GEMINI_FINALISTS", "8")), 20))
DEFAULT_MAX_WORKERS = max(1, min(int(os.getenv("IIOS_9E_GEMINI_WORKERS", "4")), 8))
DEFAULT_THINKING_LEVEL = str(os.getenv("IIOS_9E_GEMINI_THINKING", "medium")).strip().lower()

RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "research_score": {"type": "number"},
        "verified_catalysts": {"type": "array", "items": {"type": "string"}},
        "counterevidence": {"type": "array", "items": {"type": "string"}},
        "primary_sources_found": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "research_summary": {"type": "string"},
        "complexity_score": {"type": "number"},
    },
    "required": [
        "ticker",
        "research_score",
        "verified_catalysts",
        "counterevidence",
        "primary_sources_found",
        "open_questions",
        "research_summary",
        "complexity_score",
    ],
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, number))


def _string_list(value: Any, *, limit: int = 20, chars: int = 800) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x)[:chars] for x in value if str(x).strip()][:limit]


def _system_prompt() -> str:
    return (
        "You are Gemini operating as IIOS's source-grounded pre-case Research Crew. "
        "Use Google Search grounding and URL Context at full useful capability. Verify the current catalyst, seek primary sources, "
        "separate fact from inference, identify what changed versus what was already known, test the strongest confirming and "
        "contradicting explanations, and state unresolved evidence gaps. Do not recommend or execute a trade. "
        "Score research priority, not expected return. Return only the required structured research packet."
    )


def research_one(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("Gemini finalist missing ticker")
    result = gemini_provider.research_json(
        system=_system_prompt(),
        user=json.dumps(
            {
                "objective": "Determine whether this radar candidate deserves immediate governed IIOS case research.",
                "candidate": row,
            },
            ensure_ascii=False,
            default=str,
        ),
        schema=RESEARCH_SCHEMA,
        model=gemini_provider.flash_model(),
        thinking_level=(
            DEFAULT_THINKING_LEVEL
            if DEFAULT_THINKING_LEVEL in {"low", "medium", "high"}
            else "medium"
        ),
        use_google_search=True,
        use_url_context=True,
        max_output_tokens=8000,
    )
    value = result.get("output") or {}
    if not isinstance(value, dict):
        raise ValueError("Gemini research output is not a JSON object")
    resolved = str(value.get("ticker") or ticker).strip().upper()
    if resolved != ticker:
        raise ValueError(f"Gemini ticker mismatch: expected {ticker}, got {resolved}")
    return {
        "ticker": ticker,
        "research_score": _safe_float(value.get("research_score")),
        "verified_catalysts": _string_list(value.get("verified_catalysts")),
        "counterevidence": _string_list(value.get("counterevidence")),
        "primary_sources_found": _string_list(value.get("primary_sources_found")),
        "open_questions": _string_list(value.get("open_questions")),
        "research_summary": str(value.get("research_summary") or "")[:5000],
        "complexity_score": _safe_float(value.get("complexity_score")),
        "provider_model": result.get("model"),
        "latency_ms": result.get("latency_ms"),
        "usage": result.get("usage") or {},
        "web_search_queries": result.get("web_search_queries") or [],
        "grounding_sources": result.get("grounding_sources") or [],
        "url_context_metadata": result.get("url_context_metadata") or {},
        "google_search_enabled": True,
        "url_context_enabled": True,
        "context_only": True,
        "qualification_evidence": False,
        "fact_resolution_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def run_gemini_rapid_research(
    rows: list[dict[str, Any]],
    *,
    finalist_count: int = DEFAULT_FINALIST_COUNT,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    output: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    finalists = rows[: max(1, min(int(finalist_count), 20))]
    if not finalists:
        return output, errors

    # One cheap canary prevents many parallel failures when credentials, quota,
    # billing, or model access are unavailable.
    try:
        gemini_provider.preflight()
    except Exception as exc:  # noqa: BLE001
        return {}, {"PREFLIGHT": f"{type(exc).__name__}: {exc}"[:2500]}

    with ThreadPoolExecutor(max_workers=min(max(1, int(max_workers)), len(finalists))) as pool:
        future_map = {
            pool.submit(research_one, row): str(row.get("ticker") or "").upper()
            for row in finalists
        }
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                result = future.result()
                output[ticker] = result
            except Exception as exc:  # noqa: BLE001
                errors[ticker or "UNKNOWN"] = f"{type(exc).__name__}: {exc}"[:2500]

    return output, errors
