#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts" / "iios_brain_shadow_bakeoff.py"
CONFIG_PATH = ROOT / "config" / "iios_batch10m5_brain_shadow_bakeoff.json"
BACKEND = ROOT / "BACK END" / "backend"
APP = Path.home() / "Library" / "Application Support" / "IIOS"
LATEST = APP / "brain-shadow-bakeoff" / "latest_brain_shadow_bakeoff.json"
FALLBACK_DEFAULT = "gemini-3.6-flash"
FALLBACK_TIMEOUT_SECONDS = "180"
FALLBACK_RETRIES = "1"

RESEARCH_SCHEMA = {
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


def _load_base():
    spec = importlib.util.spec_from_file_location("batch10m5_base", BASE_SCRIPT)
    if not spec or not spec.loader:
        raise SystemExit("Unable to load Batch 10M.5 base runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Unable to read {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return value


def _install_ca_bundle() -> str:
    try:
        import certifi
    except Exception as exc:
        raise SystemExit(f"certifi is required in the IIOS backend venv: {type(exc).__name__}: {exc}") from exc
    bundle = str(certifi.where())
    if not Path(bundle).exists():
        raise SystemExit(f"certifi CA bundle missing: {bundle}")
    os.environ["SSL_CERT_FILE"] = bundle
    os.environ["REQUESTS_CA_BUNDLE"] = bundle
    return bundle


def _import_gemini_provider():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    import gemini_provider

    return gemini_provider


def _fallback_model() -> str:
    return str(os.getenv("IIOS_9E_GEMINI_FALLBACK_MODEL") or FALLBACK_DEFAULT).strip()


def _fallback_call(base, gemini_provider, prompt: str, row: dict) -> dict:
    level = str(row.get("thinking_level") or "medium")
    primary_model = str(row.get("model") or gemini_provider.flash_model())
    primary_error = str(row.get("error") or "PRIMARY_GEMINI_SHADOW_FAILED")[:2500]
    fallback_model = _fallback_model()

    try:
        result = gemini_provider.research_json(
            system=(
                "You are a SHADOW IIOS grounded-research evaluator operating as an explicit Gemini fallback lane. "
                "Use Google Search grounding and URL Context. Return only the requested structured research packet. "
                "Do not recommend or execute a trade and do not alter production state."
            ),
            user=prompt,
            schema=RESEARCH_SCHEMA,
            model=fallback_model,
            thinking_level=level,
            use_google_search=True,
            use_url_context=True,
            max_output_tokens=8000,
        )
        raw = {
            "status": "COMPLETE",
            "provider": "GOOGLE",
            "model": result.get("model") or fallback_model,
            "thinking_level": level,
            "latency_ms": result.get("latency_ms"),
            "usage": result.get("usage") or {},
            "grounding_sources": result.get("grounding_sources") or [],
            "output": result.get("output") or {},
            "fallback_used": True,
            "preferred_model": primary_model,
            "preferred_model_error": primary_error,
            "fallback_model": fallback_model,
            "fallback_reason": "PRIMARY_GEMINI_TRANSIENT_AVAILABILITY_FAILURE",
        }
    except Exception as exc:
        raw = {
            "status": "FAILED_CLOSED",
            "provider": "GOOGLE",
            "model": fallback_model,
            "thinking_level": level,
            "fallback_used": True,
            "preferred_model": primary_model,
            "preferred_model_error": primary_error,
            "fallback_model": fallback_model,
            "fallback_reason": "PRIMARY_GEMINI_TRANSIENT_AVAILABILITY_FAILURE",
            "error": f"{type(exc).__name__}: {exc}"[:2500],
        }
    return base.annotate_result(raw, "research")


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry only failed Gemini lanes through the explicit configured fallback model")
    parser.add_argument("--confirm-shadow-provider-spend", action="store_true")
    args = parser.parse_args()
    if not args.confirm_shadow_provider_spend:
        raise SystemExit("Fallback retry refused: add --confirm-shadow-provider-spend to acknowledge bounded provider API usage")

    config = _read_json(CONFIG_PATH)
    prior = _read_json(LATEST)
    if prior.get("status") != "SHADOW_BAKEOFF_COMPLETE":
        raise SystemExit("Latest artifact is not a completed shadow bakeoff")
    cases = [row for row in prior.get("cases") or [] if isinstance(row, dict)]
    if len(cases) != 1:
        raise SystemExit("Gemini fallback retry currently requires exactly one smoke-test case")

    base = _load_base()
    ca_bundle = _install_ca_bundle()
    base.load_dotenv(base.expand(str(config.get("live_env_path") or "")))
    os.environ["IIOS_GEMINI_TIMEOUT_SECONDS"] = FALLBACK_TIMEOUT_SECONDS
    os.environ["IIOS_GEMINI_RETRIES"] = FALLBACK_RETRIES
    gemini_provider = _import_gemini_provider()

    case_id = str(cases[0].get("case_id") or "")
    ledger = base.expand(str(config.get("live_ledger_path") or ""))
    packets = base.load_completed_case_packets(ledger, 100)
    packet = next((row for row in packets if str(row.get("case_id") or "") == case_id), None)
    if not packet:
        raise SystemExit(f"Unable to reload original shadow case packet: {case_id}")

    case = dict(cases[0])
    prompt = base.research_prompt(packet)

    fallback_calls = 0
    gemini_rows: list[dict] = []
    for row in case.get("gemini_thinking_variants") or []:
        if isinstance(row, dict) and row.get("status") == "FAILED_CLOSED":
            gemini_rows.append(_fallback_call(base, gemini_provider, prompt, row))
            fallback_calls += 1
        else:
            gemini_rows.append(row)
    case["gemini_thinking_variants"] = gemini_rows

    grok_rows = [row for row in case.get("grok_reasoning_variants") or [] if isinstance(row, dict)]
    grok_source = next((r for r in reversed(grok_rows) if r.get("status") == "COMPLETE"), None)
    gemini_source = next((r for r in reversed(gemini_rows) if isinstance(r, dict) and r.get("status") == "COMPLETE"), None)

    arbiter_calls = 0
    arbiter = case.get("multi_model_arbiter") if isinstance(case.get("multi_model_arbiter"), dict) else {}
    if arbiter.get("status") == "SKIPPED" and grok_source and gemini_source:
        arbiter_cfg = (config.get("experiments") or {}).get("multi_model_arbiter") or {}
        arbiter_packet = {
            "case_id": packet["case_id"],
            "topic": packet["topic"],
            "production_specialists": packet["specialists"],
            "grok_shadow_research": grok_source.get("output"),
            "gemini_shadow_research": gemini_source.get("output"),
            "gemini_model_identity": {
                "model": gemini_source.get("model"),
                "fallback_used": gemini_source.get("fallback_used") is True,
                "preferred_model": gemini_source.get("preferred_model"),
                "fallback_model": gemini_source.get("fallback_model"),
            },
        }
        prompt2 = (
            "You are a SHADOW multi-model IIOS arbiter. Compare independent Grok and Gemini research against the supplied governed specialist context. "
            "The packet explicitly records whether Gemini used its fallback model; preserve that distinction in your reasoning. "
            "Resolve contradictions without assuming either provider is correct. Return ONLY JSON with summary, agreement, dissent, bull_case, bear_case, required_evidence, confidence, disposition, decision_rationale. "
            "WATCH or NO_TRADE only. No live authority.\n\nPACKET:\n" + json.dumps(arbiter_packet, ensure_ascii=False, default=str)
        )
        production_disposition = str((packet.get("production_committee") or {}).get("disposition") or "") or None
        arbiter = base.call_openai(
            prompt2,
            str(arbiter_cfg.get("model") or "gpt-5.6-terra"),
            str(arbiter_cfg.get("reasoning_effort") or "high"),
        )
        arbiter = base.annotate_result(arbiter, "committee", production_disposition)
        arbiter["gemini_fallback_input_used"] = gemini_source.get("fallback_used") is True
        arbiter["gemini_model_used"] = gemini_source.get("model")
        arbiter_calls = 1
    case["multi_model_arbiter"] = arbiter

    result_cases = [case]
    payload = dict(prior)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["cases"] = result_cases
    payload["summary"] = base.build_summary(result_cases)
    payload["retry"] = {
        "mode": "FAILED_GEMINI_FALLBACK_ONLY",
        "provider_calls_this_retry": fallback_calls + arbiter_calls,
        "gemini_fallback_calls": fallback_calls,
        "arbiter_calls": arbiter_calls,
        "openai_committee_calls_repeated": 0,
        "completed_grok_calls_repeated": 0,
        "primary_gemini_calls_repeated": 0,
        "fallback_model_requested": _fallback_model(),
        "ca_bundle": ca_bundle,
        "fallback_timeout_seconds": int(FALLBACK_TIMEOUT_SECONDS),
        "fallback_request_retries": int(FALLBACK_RETRIES),
        "production_gemini_runtime_changed": False,
    }
    payload["production_routing_state"] = "UNCHANGED"
    payload["ledger_mode"] = "READ_ONLY"
    payload["ledger_write"] = False
    payload["auto_apply"] = False
    payload["human_review_required"] = True
    payload["trade_execution_permission"] = False
    payload["live_execution"] = False

    output_dir = Path.home() / "Library" / "Application Support" / "IIOS" / "brain-shadow-bakeoff"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base.write_json(output_dir / f"brain_shadow_bakeoff_gemini_fallback_{stamp}.json", payload)
    base.write_json(LATEST, payload)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
