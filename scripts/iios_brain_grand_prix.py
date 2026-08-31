#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts" / "iios_brain_shadow_bakeoff.py"
DEFAULT_CONFIG = ROOT / "config" / "iios_batch10m6_brain_grand_prix.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expand(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_base():
    spec = importlib.util.spec_from_file_location("batch10m5_base", BASE_SCRIPT)
    if not spec or not spec.loader:
        raise SystemExit("Unable to load Batch 10M.5 base runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_ca_bundle() -> str:
    try:
        import certifi
    except Exception as exc:
        raise SystemExit(f"certifi required: {type(exc).__name__}: {exc}") from exc
    bundle = str(certifi.where())
    if not Path(bundle).exists():
        raise SystemExit(f"certifi CA bundle missing: {bundle}")
    os.environ["SSL_CERT_FILE"] = bundle
    os.environ["REQUESTS_CA_BUNDLE"] = bundle
    return bundle


def select_cases(packets: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for packet in packets:
        topic = " ".join(str(packet.get("topic") or "").lower().split())
        if topic and topic not in seen_topics:
            selected.append(packet)
            seen_topics.add(topic)
        if len(selected) >= limit:
            return selected
    selected_ids = {str(x.get("case_id") or "") for x in selected}
    for packet in packets:
        if str(packet.get("case_id") or "") in selected_ids:
            continue
        selected.append(packet)
        if len(selected) >= limit:
            break
    return selected


def research_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "catalyst_summary": {"type": "string"},
            "strongest_evidence": {"type": "array", "items": {"type": "string"}},
            "contradictions": {"type": "array", "items": {"type": "string"}},
            "evidence_gaps": {"type": "array", "items": {"type": "string"}},
            "primary_sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
        },
        "required": [
            "catalyst_summary",
            "strongest_evidence",
            "contradictions",
            "evidence_gaps",
            "primary_sources",
            "confidence",
        ],
    }


def call_gemini_model(base, prompt: str, thinking_level: str, model: str, *, fallback_used: bool, primary_error: str | None = None) -> dict[str, Any]:
    if str(base.BACKEND) not in sys.path:
        sys.path.insert(0, str(base.BACKEND))
    try:
        import gemini_provider
    except Exception as exc:
        return {
            "status": "FAILED_CLOSED",
            "provider": "GOOGLE",
            "model": model,
            "thinking_level": thinking_level,
            "fallback_used": fallback_used,
            "error": f"GEMINI_IMPORT_FAILED: {type(exc).__name__}: {exc}"[:2500],
        }
    started = time.perf_counter()
    try:
        result = gemini_provider.research_json(
            system="You are a SHADOW IIOS grounded-research evaluator. Use Google Search and URL Context. Do not recommend or execute a trade.",
            user=prompt,
            schema=research_schema(),
            model=model,
            thinking_level=thinking_level,
            use_google_search=True,
            use_url_context=True,
            max_output_tokens=8000,
        )
        row = {
            "status": "COMPLETE",
            "provider": "GOOGLE",
            "model": result.get("model") or model,
            "thinking_level": thinking_level,
            "latency_ms": result.get("latency_ms") or round((time.perf_counter() - started) * 1000.0, 1),
            "usage": result.get("usage") or {},
            "grounding_sources": result.get("grounding_sources") or [],
            "output": result.get("output") or {},
            "fallback_used": fallback_used,
            "primary_model_error": primary_error,
        }
        return base.annotate_result(row, "research")
    except Exception as exc:
        row = {
            "status": "FAILED_CLOSED",
            "provider": "GOOGLE",
            "model": model,
            "thinking_level": thinking_level,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 1),
            "fallback_used": fallback_used,
            "primary_model_error": primary_error,
            "error": f"{type(exc).__name__}: {exc}"[:2500],
        }
        return base.annotate_result(row, "research")


def execute_case(base, packet: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    lanes = config.get("lanes_per_case") or {}
    production_disposition = str((packet.get("production_committee") or {}).get("disposition") or "") or None
    committee: list[dict[str, Any]] = []
    for variant in lanes.get("openai_committee") or []:
        if not isinstance(variant, dict):
            continue
        result = base.call_openai(
            base.committee_prompt(packet),
            str(variant.get("model") or "gpt-5.6-luna"),
            str(variant.get("reasoning_effort") or "medium"),
        )
        committee.append(base.annotate_result(result, "committee", production_disposition))

    grok: list[dict[str, Any]] = []
    for level in lanes.get("grok_research") or []:
        grok.append(base.annotate_result(base.call_grok(base.research_prompt(packet), str(level)), "research"))

    fallback_model = str(lanes.get("gemini_fallback_model") or "gemini-3.6-flash")
    gemini: list[dict[str, Any]] = []
    for level in lanes.get("gemini_primary") or []:
        primary = base.call_gemini(base.research_prompt(packet), str(level))
        primary = base.annotate_result(primary, "research")
        if primary.get("status") == "COMPLETE" or not lanes.get("gemini_fallback_on_failed_closed"):
            primary["fallback_used"] = False
            gemini.append(primary)
            continue
        primary_error = str(primary.get("error") or "PRIMARY_GEMINI_FAILED_CLOSED")[:2500]
        fallback = call_gemini_model(
            base,
            base.research_prompt(packet),
            str(level),
            fallback_model,
            fallback_used=True,
            primary_error=primary_error,
        )
        gemini.append(fallback)

    grok_source = next((x for x in reversed(grok) if x.get("status") == "COMPLETE"), None)
    gemini_source = next((x for x in reversed(gemini) if x.get("status") == "COMPLETE"), None)
    arbiter_cfg = lanes.get("multi_model_arbiter") or {}
    if grok_source and gemini_source:
        arbiter_packet = {
            "case_id": packet["case_id"],
            "topic": packet["topic"],
            "production_specialists": packet["specialists"],
            "grok_shadow_research": grok_source.get("output"),
            "gemini_shadow_research": gemini_source.get("output"),
        }
        prompt = (
            "You are a SHADOW multi-model IIOS arbiter. Compare independent Grok and Gemini research against the supplied governed specialist context. "
            "Resolve contradictions without assuming either provider is correct. Return ONLY JSON with summary, agreement, dissent, bull_case, bear_case, required_evidence, confidence, disposition, decision_rationale. "
            "WATCH or NO_TRADE only. No live authority.\n\nPACKET:\n" + json.dumps(arbiter_packet, ensure_ascii=False, default=str)
        )
        arbiter = base.call_openai(
            prompt,
            str(arbiter_cfg.get("model") or "gpt-5.6-terra"),
            str(arbiter_cfg.get("reasoning_effort") or "high"),
        )
        arbiter = base.annotate_result(arbiter, "committee", production_disposition)
    else:
        arbiter = {
            "status": "SKIPPED",
            "reason": "COMPLETE_GROK_AND_GEMINI_OUTPUTS_REQUIRED",
            "accuracy_score": None,
            "accuracy_state": "WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE",
        }

    return {
        "case_id": packet["case_id"],
        "topic": packet.get("topic"),
        "source_decision_created_at": packet.get("source_decision_created_at"),
        "production_committee": packet.get("production_committee") or {},
        "openai_committee_variants": committee,
        "grok_reasoning_variants": grok,
        "gemini_thinking_variants": gemini,
        "multi_model_arbiter": arbiter,
    }


def evidence_gap_count(row: dict[str, Any]) -> int:
    output = row.get("output") if isinstance(row.get("output"), dict) else {}
    value = output.get("required_evidence") or output.get("evidence_gaps") or []
    return len(value) if isinstance(value, list) else 0


def lane_label(family: str, row: dict[str, Any]) -> str:
    if family == "OPENAI_COMMITTEE":
        return f"{row.get('model')}::{row.get('reasoning_effort')}"
    if family == "GROK":
        return f"{row.get('model')}::{row.get('reasoning_effort')}"
    if family == "GEMINI":
        suffix = "fallback" if row.get("fallback_used") else "primary"
        return f"{row.get('model')}::{row.get('thinking_level')}::{suffix}"
    return f"{row.get('model')}::{row.get('reasoning_effort')}"


def build_leaderboard(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for case in cases:
        for family, rows in (
            ("OPENAI_COMMITTEE", case.get("openai_committee_variants") or []),
            ("GROK", case.get("grok_reasoning_variants") or []),
            ("GEMINI", case.get("gemini_thinking_variants") or []),
        ):
            for row in rows:
                if isinstance(row, dict):
                    buckets.setdefault((family, lane_label(family, row)), []).append(row)
        arbiter = case.get("multi_model_arbiter")
        if isinstance(arbiter, dict) and arbiter.get("status") != "SKIPPED":
            buckets.setdefault(("MULTI_MODEL_ARBITER", lane_label("ARBITER", arbiter)), []).append(arbiter)

    board: list[dict[str, Any]] = []
    for (family, label), rows in buckets.items():
        complete = [x for x in rows if x.get("status") == "COMPLETE"]
        latencies = [float(x["latency_ms"]) for x in complete if x.get("latency_ms") is not None]
        completeness = [float(x["response_completeness_pct"]) for x in complete if x.get("response_completeness_pct") is not None]
        agreements = [bool(x.get("agreement_with_production_disposition")) for x in complete if "agreement_with_production_disposition" in x]
        board.append(
            {
                "family": family,
                "lane": label,
                "attempts": len(rows),
                "complete": len(complete),
                "reliability_pct": round(len(complete) / len(rows) * 100.0, 1) if rows else 0.0,
                "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
                "median_completeness_pct": round(statistics.median(completeness), 1) if completeness else None,
                "production_disposition_agreement_pct": round(sum(agreements) / len(agreements) * 100.0, 1) if agreements else None,
                "average_evidence_gap_count": round(sum(evidence_gap_count(x) for x in complete) / len(complete), 2) if complete else None,
                "accuracy_score": None,
                "accuracy_state": "WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE",
                "exact_cost_usd": None,
                "cost_state": "DO_NOT_INVENT_COST_IF_EXACT_PROVIDER_COST_IS_NOT_PERSISTED",
            }
        )
    return sorted(board, key=lambda x: (-float(x.get("reliability_pct") or 0), float(x.get("median_latency_ms") or 1e18), x["lane"]))


def planned_calls(config: dict[str, Any], case_count: int) -> dict[str, int]:
    lanes = config.get("lanes_per_case") or {}
    core_per_case = len(lanes.get("openai_committee") or []) + len(lanes.get("grok_research") or []) + len(lanes.get("gemini_primary") or []) + 1
    fallback_max = len(lanes.get("gemini_primary") or []) if lanes.get("gemini_fallback_on_failed_closed") else 0
    return {
        "core_per_case": core_per_case,
        "core_total": core_per_case * case_count,
        "fallback_max_per_case": fallback_max,
        "maximum_total": (core_per_case + fallback_max) * case_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 10M.6 Brain Grand Prix")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-shadow-provider-spend", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    config = read_json(expand(args.config))
    if not config:
        raise SystemExit("Grand Prix config missing or invalid")
    output_dir = expand(str(config.get("output_directory") or "~/Library/Application Support/IIOS/brain-grand-prix"))
    latest = output_dir / "latest_brain_grand_prix.json"
    if args.status:
        if not latest.exists():
            print(f"No Grand Prix artifact yet: {latest}")
            return 1
        print(latest.read_text(encoding="utf-8"))
        return 0

    base = load_base()
    max_cases = int(config.get("max_case_limit") or 10)
    limit = args.case_limit if args.case_limit is not None else int(config.get("default_case_limit") or 5)
    limit = max(1, min(limit, max_cases))
    ledger = expand(str(config.get("live_ledger_path") or ""))
    packets = base.load_completed_case_packets(ledger, max(limit * 5, 50))
    packets = select_cases(packets, limit)
    if not packets:
        raise SystemExit("No completed eight-agent + Committee cases available")

    call_plan = planned_calls(config, len(packets))
    hard_cap = int(config.get("max_provider_calls_per_run") or 100)
    if call_plan["maximum_total"] > hard_cap:
        raise SystemExit(f"Maximum provider calls {call_plan['maximum_total']} exceed hard cap {hard_cap}")

    plan = {
        "case_count": len(packets),
        "case_ids": [x.get("case_id") for x in packets],
        "topics": [x.get("topic") for x in packets],
        "call_plan": call_plan,
        "hard_call_cap": hard_cap,
        "lanes_per_case": config.get("lanes_per_case") or {},
        "capability_policy": config.get("capability_policy") or {},
    }

    if not args.execute:
        payload = {
            "schema_version": "batch10m6-brain-grand-prix-v1",
            "generated_at": now_iso(),
            "status": "DRY_RUN_PLAN_ONLY",
            "provider_calls_made": False,
            "plan": plan,
            "safety": config.get("safety") or {},
        }
        write_json(latest, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if not args.confirm_shadow_provider_spend:
        raise SystemExit("Execution refused: add --confirm-shadow-provider-spend to acknowledge bounded provider API usage")

    base.load_dotenv(expand(str(config.get("live_env_path") or "")))
    ca_bundle = install_ca_bundle()
    os.environ.setdefault("IIOS_GEMINI_TIMEOUT_SECONDS", "180")
    os.environ.setdefault("IIOS_GEMINI_RETRIES", "1")

    started = time.perf_counter()
    results = [execute_case(base, packet, config) for packet in packets]
    payload = {
        "schema_version": "batch10m6-brain-grand-prix-v1",
        "generated_at": now_iso(),
        "status": "BRAIN_GRAND_PRIX_COMPLETE",
        "provider_calls_made": True,
        "plan": plan,
        "cases": results,
        "leaderboard": build_leaderboard(results),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "ca_bundle": ca_bundle,
        "production_routing_state": "UNCHANGED",
        "ledger_mode": "READ_ONLY",
        "ledger_write": False,
        "auto_apply_winner": False,
        "human_review_required": True,
        "accuracy_state": "WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE",
        "trade_execution_permission": False,
        "live_execution": False,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_json(output_dir / f"brain_grand_prix_{stamp}.json", payload)
    write_json(latest, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
