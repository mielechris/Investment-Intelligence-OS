from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any

from fastapi import APIRouter


router = APIRouter()

SOURCE_TTL_SECONDS = {
    "sec_companyfacts": 15 * 60,
    "noaa_alerts": 5 * 60,
    "gdelt_news": 10 * 60,
    "fred_series": 30 * 60,
}

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()


def _cache_key(source_key: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return f"{source_key}:{canonical}"


def _get_cached(source_key: str, params: dict[str, Any]) -> tuple[dict[str, Any] | None, float | None]:
    ttl = int(SOURCE_TTL_SECONDS.get(source_key, 0))
    if ttl <= 0:
        return None, None

    key = _cache_key(source_key, params)
    now = time.time()
    with _LOCK:
        cached = _CACHE.get(key)
        if not cached:
            return None, None
        created_at, result = cached
        age = now - created_at
        if age > ttl:
            _CACHE.pop(key, None)
            return None, None
        return copy.deepcopy(result), round(age, 3)


def _store_cached(source_key: str, params: dict[str, Any], result: dict[str, Any]) -> None:
    ttl = int(SOURCE_TTL_SECONDS.get(source_key, 0))
    if ttl <= 0 or result.get("status") != "ok":
        return
    key = _cache_key(source_key, params)
    with _LOCK:
        _CACHE[key] = (time.time(), copy.deepcopy(result))


def clear_research_source_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def install_research_source_cache(module) -> None:
    """Cache successful exact-match public research-source responses.

    This layer reuses only source data. It never caches specialist judgments,
    committee decisions, sizing, authorization, paper orders, or execution.
    Market quotes are intentionally excluded because their provider layer already
    has short freshness-bound caches.
    """
    if getattr(module, "_research_source_cache_installed", False):
        return

    module._research_source_cache_installed = True
    original_ingest_sources = module.ingest_sources

    def cached_ingest_sources(requests: list[dict[str, Any]]) -> dict[str, Any]:
        source_results: list[dict[str, Any]] = []
        all_items: list[dict[str, Any]] = []
        cache_hits = 0
        cache_misses = 0

        for request in requests:
            source_key = str(request.get("source", "")).strip()
            params = request.get("params") if isinstance(request.get("params"), dict) else {}
            ttl = int(SOURCE_TTL_SECONDS.get(source_key, 0))

            cached, age = _get_cached(source_key, params)
            if cached is not None:
                result = {
                    **cached,
                    "cache_hit": True,
                    "cache_age_seconds": age,
                    "cache_ttl_seconds": ttl,
                    "served_at": module.utc_now(),
                }
                cache_hits += 1
            else:
                single = original_ingest_sources([request])
                rows = single.get("source_results") or []
                if rows:
                    result = copy.deepcopy(rows[0])
                else:
                    result = {
                        "source_key": source_key,
                        "status": "error",
                        "fetched_at": module.utc_now(),
                        "items": [],
                        "error": "Source ingestion returned no result",
                    }
                result["cache_hit"] = False
                result["cache_age_seconds"] = 0.0
                result["cache_ttl_seconds"] = ttl
                if ttl > 0:
                    cache_misses += 1
                _store_cached(source_key, params, result)

            source_results.append(result)
            all_items.extend(result.get("items") or [])

        return {
            "fetched_at": module.utc_now(),
            "requested_sources": len(requests),
            "successful_sources": sum(1 for row in source_results if row.get("status") == "ok"),
            "failed_sources": sum(1 for row in source_results if row.get("status") != "ok"),
            "evidence_items": all_items,
            "source_results": source_results,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_enabled": True,
            "judgment_output_cache": False,
            "paper_mode": True,
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    module.ingest_sources = cached_ingest_sources


@router.get("/research-source-cache/plan")
def research_source_cache_plan():
    return {
        "source_ttl_seconds": dict(SOURCE_TTL_SECONDS),
        "quote_cache_layer": "provider_managed_only",
        "exact_request_match_required": True,
        "cache_successes_only": True,
        "judgment_output_cache": False,
        "paper_mode": True,
        "auto_trade_authority": False,
        "paper_order_permission": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
