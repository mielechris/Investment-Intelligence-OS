#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "iios_batch10m5_brain_shadow_bakeoff.json"
BACKEND = ROOT / "BACK END" / "backend"


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


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_payload(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def load_completed_case_packets(ledger: Path, limit: int) -> list[dict[str, Any]]:
    if not ledger.exists():
        raise SystemExit(f"Live ledger not found: {ledger}")
    db = connect_ro(ledger)
    try:
        decisions = db.execute(
            "SELECT case_id,payload_json,created_at FROM ledger_objects "
            "WHERE object_type='committee_decision' ORDER BY created_at DESC LIMIT 250"
        ).fetchall()
        packets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in decisions:
            case_id = str(row["case_id"] or "")
            if not case_id or case_id in seen:
                continue
            decision = parse_payload(row["payload_json"])
            agents = decision.get("agents") if isinstance(decision.get("agents"), dict) else {}
            if len(agents) < 8:
                continue
            case_row = db.execute(
                "SELECT payload_json FROM ledger_objects WHERE case_id=? AND object_type='case' "
                "ORDER BY created_at DESC LIMIT 1",
                (case_id,),
            ).fetchone()
            if not case_row:
                continue
            case = parse_payload(case_row["payload_json"])
            evidence = case.get("evidence") if isinstance(case.get("evidence"), list) else []
            summary = decision.get("evidence_summary") if isinstance(decision.get("evidence_summary"), dict) else case.get("evidence_summary") or {}
            packets.append(
                {
                    "case_id": case_id,
                    "topic": str(case.get("topic") or decision.get("topic") or ""),
                    "evidence": evidence,
                    "evidence_summary": summary,
                    "specialists": agents,
                    "production_committee": {
                        "decision_id": decision.get("decision_id"),
                        "disposition": decision.get("disposition"),
                        "confidence": decision.get("confidence"),
                        "summary": decision.get("summary"),
                        "dissent": decision.get("dissent"),
                        "required_evidence": decision.get("required_evidence") or [],
                    },
                    "source_decision_created_at": str(row["created_at"] or ""),
                }
            )
            seen.add(case_id)
            if len(packets) >= limit:
                break
        return packets
    finally:
        db.close()


def selected_openai_variants(config: dict[str, Any], profile: str) -> list[dict[str, str]]:
    experiments = config.get("experiments") or {}
    rows = list(experiments.get("openai_committee_smoke") or [])
    if profile == "standard":
        rows.extend(experiments.get("openai_committee_standard_extra") or [])
    return [
        {"model": str(x.get("model") or ""), "reasoning_effort": str(x.get("reasoning_effort") or "medium")}
        for x in rows if isinstance(x, dict) and x.get("model")
    ]


def build_plan(config: dict[str, Any], packets: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    experiments = config.get("experiments") or {}
    openai_variants = selected_openai_variants(config, profile)
    grok_levels = [str(x) for x in experiments.get("grok_reasoning") or []]
    gemini_levels = [str(x) for x in experiments.get("gemini_thinking") or []]
    per_case = len(openai_variants) + len(grok_levels) + len(gemini_levels) + 1
    total = per_case * len(packets)
    cap = int(config.get("max_provider_calls_per_run") or 30)
    if total > cap:
        raise SystemExit(f"Planned provider calls {total} exceed hard cap {cap}")
    return {
        "profile": profile,
        "case_count": len(packets),
        "case_ids": [p["case_id"] for p in packets],
        "openai_committee_variants": openai_variants,
        "grok_reasoning_levels": grok_levels,
        "gemini_thinking_levels": gemini_levels,
        "multi_model_arbiter": experiments.get("multi_model_arbiter") or {},
        "planned_provider_calls": total,
        "hard_call_cap": cap,
        "note": "Multi-model arbiter is called once per case only after Grok and Gemini shadow research are both available.",
    }


def json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("provider output was not a JSON object")
    return parsed


def usage_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    return {}


def committee_prompt(packet: dict[str, Any]) -> str:
    body = {
        "case_id": packet["case_id"],
        "topic": packet["topic"],
        "evidence_summary": packet["evidence_summary"],
        "specialists": packet["specialists"],
    }
    return (
        "You are a SHADOW Investment Committee evaluator. This is an offline replay of an already-completed PAPER-ONLY IIOS case. "
        "Use exactly the supplied case packet. Do not research externally, do not execute or recommend a live trade, and do not change any production state. "
        "Synthesize rather than average; preserve dissent; separate evidence, inference, contradictions, and unknowns. "
        "Return ONLY JSON with fields summary, agreement, dissent, bull_case, bear_case, required_evidence, confidence, disposition, decision_rationale. "
        "Disposition must be WATCH or NO_TRADE.\n\nCASE PACKET:\n" + json.dumps(body, ensure_ascii=False, default=str)
    )


def research_prompt(packet: dict[str, Any]) -> str:
    body = {
        "case_id": packet["case_id"],
        "topic": packet["topic"],
        "evidence_summary": packet["evidence_summary"],
        "evidence": packet["evidence"][:40],
    }
    return (
        "This is a SHADOW research replay for an already-completed PAPER-ONLY IIOS case. Independently investigate only to assess research capability. "
        "Return JSON with catalyst_summary, strongest_evidence, contradictions, evidence_gaps, primary_sources, confidence. "
        "Do not recommend or execute a trade.\n\nCASE:\n" + json.dumps(body, ensure_ascii=False, default=str)
    )


def call_openai(prompt: str, model: str, effort: str) -> dict[str, Any]:
    from openai import OpenAI

    started = time.perf_counter()
    try:
        response = OpenAI().responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": effort},
        )
        latency = round((time.perf_counter() - started) * 1000.0, 1)
        output = json_object(str(response.output_text or ""))
        return {"status": "COMPLETE", "model": model, "reasoning_effort": effort, "latency_ms": latency, "usage": usage_dict(getattr(response, "usage", None)), "output": output}
    except Exception as exc:
        return {"status": "FAILED_CLOSED", "model": model, "reasoning_effort": effort, "latency_ms": round((time.perf_counter() - started) * 1000.0, 1), "error": f"{type(exc).__name__}: {exc}"[:2500]}


def grok_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return str(response.get("output_text") or "")
    parts: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def call_grok(prompt: str, effort: str) -> dict[str, Any]:
    key = str(os.getenv("IIOS_GROK_API_KEY") or os.getenv("XAI_API_KEY") or "").strip()
    if not key:
        return {"status": "FAILED_CLOSED", "provider": "XAI", "reasoning_effort": effort, "error": "GROK_PROVIDER_NOT_CONFIGURED"}
    base = str(os.getenv("IIOS_GROK_BASE_URL") or os.getenv("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")
    model = str(os.getenv("IIOS_GROK_MODEL") or "grok-4.6")
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "You are the SHADOW IIOS Wire Room. Use X Search and Web Search for independent current-context research. Return only the requested JSON. No trading authority."},
            {"role": "user", "content": prompt},
        ],
        "tools": [{"type": "web_search"}, {"type": "x_search"}],
        "reasoning_effort": effort,
        "max_output_tokens": 2000,
        "max_tool_calls": 3,
        "store": False,
    }
    started = time.perf_counter()
    request = Request(
        base + "/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
        value = json.loads(raw)
        output = json_object(grok_output_text(value))
        return {"status": "COMPLETE", "provider": "XAI", "model": value.get("model") or model, "reasoning_effort": effort, "latency_ms": round((time.perf_counter() - started) * 1000.0, 1), "usage": value.get("usage") or {}, "output": output}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return {"status": "FAILED_CLOSED", "provider": "XAI", "model": model, "reasoning_effort": effort, "latency_ms": round((time.perf_counter() - started) * 1000.0, 1), "error": f"{type(exc).__name__}: {exc}"[:2500]}


def call_gemini(prompt: str, thinking_level: str) -> dict[str, Any]:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    try:
        import gemini_provider
    except Exception as exc:
        return {"status": "FAILED_CLOSED", "provider": "GOOGLE", "thinking_level": thinking_level, "error": f"GEMINI_IMPORT_FAILED: {type(exc).__name__}: {exc}"[:2500]}
    schema = {
        "type": "object",
        "properties": {
            "catalyst_summary": {"type": "string"},
            "strongest_evidence": {"type": "array", "items": {"type": "string"}},
            "contradictions": {"type": "array", "items": {"type": "string"}},
            "evidence_gaps": {"type": "array", "items": {"type": "string"}},
            "primary_sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"}
        },
        "required": ["catalyst_summary", "strongest_evidence", "contradictions", "evidence_gaps", "primary_sources", "confidence"]
    }
    started = time.perf_counter()
    try:
        result = gemini_provider.research_json(
            system="You are a SHADOW IIOS grounded-research evaluator. Use Google Search and URL Context. Do not recommend or execute a trade.",
            user=prompt,
            schema=schema,
            model=gemini_provider.flash_model(),
            thinking_level=thinking_level,
            use_google_search=True,
            use_url_context=True,
            max_output_tokens=8000,
        )
        return {"status": "COMPLETE", "provider": "GOOGLE", "model": result.get("model"), "thinking_level": thinking_level, "latency_ms": result.get("latency_ms") or round((time.perf_counter() - started) * 1000.0, 1), "usage": result.get("usage") or {}, "grounding_sources": result.get("grounding_sources") or [], "output": result.get("output") or {}}
    except Exception as exc:
        return {"status": "FAILED_CLOSED", "provider": "GOOGLE", "thinking_level": thinking_level, "latency_ms": round((time.perf_counter() - started) * 1000.0, 1), "error": f"{type(exc).__name__}: {exc}"[:2500]}


def completeness(output: dict[str, Any], required: list[str]) -> float:
    if not isinstance(output, dict) or not required:
        return 0.0
    return round(sum(1 for key in required if output.get(key) not in (None, "", [], {})) / len(required) * 100.0, 1)


def annotate_result(result: dict[str, Any], kind: str, production_disposition: str | None = None) -> dict[str, Any]:
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    if kind == "committee":
        required = ["summary", "dissent", "bull_case", "bear_case", "required_evidence", "confidence", "disposition"]
    else:
        required = ["catalyst_summary", "strongest_evidence", "contradictions", "evidence_gaps", "confidence"]
    result = dict(result)
    result["response_completeness_pct"] = completeness(output, required)
    if kind == "committee":
        disposition = str(output.get("disposition") or "")
        result["disposition"] = disposition or None
        result["agreement_with_production_disposition"] = bool(production_disposition and disposition == production_disposition)
        result["agreement_is_not_accuracy"] = True
    result["accuracy_score"] = None
    result["accuracy_state"] = "WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE"
    return result


def execute_case(packet: dict[str, Any], config: dict[str, Any], profile: str) -> dict[str, Any]:
    experiments = config.get("experiments") or {}
    production_disposition = str((packet.get("production_committee") or {}).get("disposition") or "") or None
    committee_results: list[dict[str, Any]] = []
    for variant in selected_openai_variants(config, profile):
        result = call_openai(committee_prompt(packet), variant["model"], variant["reasoning_effort"])
        committee_results.append(annotate_result(result, "committee", production_disposition))

    grok_results: list[dict[str, Any]] = []
    for level in experiments.get("grok_reasoning") or []:
        result = call_grok(research_prompt(packet), str(level))
        grok_results.append(annotate_result(result, "research"))

    gemini_results: list[dict[str, Any]] = []
    for level in experiments.get("gemini_thinking") or []:
        result = call_gemini(research_prompt(packet), str(level))
        gemini_results.append(annotate_result(result, "research"))

    grok_source = next((r for r in reversed(grok_results) if r.get("status") == "COMPLETE"), None)
    gemini_source = next((r for r in reversed(gemini_results) if r.get("status") == "COMPLETE"), None)
    arbiter_cfg = experiments.get("multi_model_arbiter") or {}
    if grok_source and gemini_source and arbiter_cfg.get("model"):
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
        arbiter = call_openai(prompt, str(arbiter_cfg.get("model")), str(arbiter_cfg.get("reasoning_effort") or "high"))
        arbiter = annotate_result(arbiter, "committee", production_disposition)
    else:
        arbiter = {"status": "SKIPPED", "reason": "GROK_AND_GEMINI_COMPLETE_OUTPUTS_REQUIRED", "accuracy_score": None, "accuracy_state": "WAITING_FOR_EXACT_TASK_TO_OUTCOME_LINKAGE"}

    return {
        "case_id": packet["case_id"],
        "topic": packet["topic"],
        "source_decision_created_at": packet["source_decision_created_at"],
        "production_committee": packet["production_committee"],
        "openai_committee_variants": committee_results,
        "grok_reasoning_variants": grok_results,
        "gemini_thinking_variants": gemini_results,
        "multi_model_arbiter": arbiter,
    }


def build_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    for case in case_results:
        calls.extend(case.get("openai_committee_variants") or [])
        calls.extend(case.get("grok_reasoning_variants") or [])
        calls.extend(case.get("gemini_thinking_variants") or [])
        if isinstance(case.get("multi_model_arbiter"), dict) and case["multi_model_arbiter"].get("status") != "SKIPPED":
            calls.append(case["multi_model_arbiter"])
    complete = [x for x in calls if x.get("status") == "COMPLETE"]
    failed = [x for x in calls if x.get("status") == "FAILED_CLOSED"]
    latencies = [float(x["latency_ms"]) for x in complete if x.get("latency_ms") is not None]
    return {
        "provider_call_count": len(calls),
        "complete_count": len(complete),
        "failed_closed_count": len(failed),
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "exact_cost_usd": None,
        "cost_state": "DO_NOT_INVENT_COST_IF_PROVIDER_EXACT_COST_IS_NOT_PERSISTED",
        "accuracy_state": "NO_ACCURACY_CLAIM_UNTIL_EXACT_TASK_TO_OUTCOME_LINKAGE",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Batch 10M.5 Brain Shadow Bakeoff")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--profile", choices=("smoke", "standard"), default=None)
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-shadow-provider-spend", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    config = read_json(expand(args.config))
    if not config:
        raise SystemExit("Bakeoff config missing or invalid")
    output_dir = expand(str(config.get("output_directory") or "~/Library/Application Support/IIOS/brain-shadow-bakeoff"))
    latest = output_dir / "latest_brain_shadow_bakeoff.json"
    if args.status:
        if latest.exists():
            print(latest.read_text(encoding="utf-8"))
            return 0
        print(f"No bakeoff artifact yet: {latest}")
        return 1

    profile = args.profile or str(config.get("default_profile") or "smoke")
    max_cases = int(config.get("max_case_limit") or 3)
    case_limit = args.case_limit if args.case_limit is not None else int(config.get("default_case_limit") or 1)
    case_limit = max(1, min(case_limit, max_cases))
    ledger = expand(str(config.get("live_ledger_path") or ""))
    env_path = expand(str(config.get("live_env_path") or ""))
    packets = load_completed_case_packets(ledger, case_limit)
    if not packets:
        raise SystemExit("No completed eight-agent + Committee case packets available for shadow replay")
    plan = build_plan(config, packets, profile)

    if not args.execute:
        payload = {
            "schema_version": "batch10m5-brain-shadow-bakeoff-v1",
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

    load_dotenv(env_path)
    started = time.perf_counter()
    results = [execute_case(packet, config, profile) for packet in packets]
    payload = {
        "schema_version": "batch10m5-brain-shadow-bakeoff-v1",
        "generated_at": now_iso(),
        "status": "SHADOW_BAKEOFF_COMPLETE",
        "profile": profile,
        "plan": plan,
        "cases": results,
        "summary": build_summary(results),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "production_routing_state": "UNCHANGED",
        "ledger_mode": "READ_ONLY",
        "ledger_write": False,
        "provider_calls_made": True,
        "auto_apply": False,
        "human_review_required": True,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_json(output_dir / f"brain_shadow_bakeoff_{stamp}.json", payload)
    write_json(latest, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
