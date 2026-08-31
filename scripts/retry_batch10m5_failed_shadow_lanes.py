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
APP = Path.home() / "Library" / "Application Support" / "IIOS"
LATEST = APP / "brain-shadow-bakeoff" / "latest_brain_shadow_bakeoff.json"


def _load_module():
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


def _replace_failed(existing: list[dict], retry_fn) -> tuple[list[dict], int]:
    out: list[dict] = []
    calls = 0
    for row in existing:
        if not isinstance(row, dict) or row.get("status") != "FAILED_CLOSED":
            out.append(row)
            continue
        out.append(retry_fn(row))
        calls += 1
    return out, calls


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry only failed Batch 10M.5 Grok/Gemini shadow lanes")
    parser.add_argument("--confirm-shadow-provider-spend", action="store_true")
    args = parser.parse_args()
    if not args.confirm_shadow_provider_spend:
        raise SystemExit("Retry refused: add --confirm-shadow-provider-spend to acknowledge bounded provider API usage")

    config = _read_json(CONFIG_PATH)
    prior = _read_json(LATEST)
    if prior.get("status") != "SHADOW_BAKEOFF_COMPLETE":
        raise SystemExit("Latest artifact is not a completed shadow bakeoff")
    cases = [row for row in prior.get("cases") or [] if isinstance(row, dict)]
    if len(cases) != 1:
        raise SystemExit("Failed-lane retry currently requires exactly one smoke-test case")

    base = _load_module()
    ca_bundle = _install_ca_bundle()
    base.load_dotenv(base.expand(str(config.get("live_env_path") or "")))

    case_id = str(cases[0].get("case_id") or "")
    ledger = base.expand(str(config.get("live_ledger_path") or ""))
    packets = base.load_completed_case_packets(ledger, 100)
    packet = next((row for row in packets if str(row.get("case_id") or "") == case_id), None)
    if not packet:
        raise SystemExit(f"Unable to reload original shadow case packet: {case_id}")

    case = dict(cases[0])
    prompt = base.research_prompt(packet)

    def retry_grok(row: dict) -> dict:
        level = str(row.get("reasoning_effort") or "medium")
        return base.annotate_result(base.call_grok(prompt, level), "research")

    def retry_gemini(row: dict) -> dict:
        level = str(row.get("thinking_level") or "medium")
        return base.annotate_result(base.call_gemini(prompt, level), "research")

    grok, grok_calls = _replace_failed(case.get("grok_reasoning_variants") or [], retry_grok)
    gemini, gemini_calls = _replace_failed(case.get("gemini_thinking_variants") or [], retry_gemini)
    case["grok_reasoning_variants"] = grok
    case["gemini_thinking_variants"] = gemini

    arbiter_calls = 0
    arbiter = case.get("multi_model_arbiter") if isinstance(case.get("multi_model_arbiter"), dict) else {}
    grok_source = next((r for r in reversed(grok) if isinstance(r, dict) and r.get("status") == "COMPLETE"), None)
    gemini_source = next((r for r in reversed(gemini) if isinstance(r, dict) and r.get("status") == "COMPLETE"), None)
    if arbiter.get("status") == "SKIPPED" and grok_source and gemini_source:
        arbiter_cfg = (config.get("experiments") or {}).get("multi_model_arbiter") or {}
        arbiter_packet = {
            "case_id": packet["case_id"],
            "topic": packet["topic"],
            "production_specialists": packet["specialists"],
            "grok_shadow_research": grok_source.get("output"),
            "gemini_shadow_research": gemini_source.get("output"),
        }
        prompt2 = (
            "You are a SHADOW multi-model IIOS arbiter. Compare independent Grok and Gemini research against the supplied governed specialist context. "
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
        arbiter_calls = 1
    case["multi_model_arbiter"] = arbiter

    result_cases = [case]
    payload = dict(prior)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload["cases"] = result_cases
    payload["summary"] = base.build_summary(result_cases)
    payload["retry"] = {
        "mode": "FAILED_GROK_GEMINI_LANES_ONLY",
        "provider_calls_this_retry": grok_calls + gemini_calls + arbiter_calls,
        "openai_committee_calls_repeated": 0,
        "ca_bundle": ca_bundle,
        "ssl_cert_file_set": True,
        "requests_ca_bundle_set": True,
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
    base.write_json(output_dir / f"brain_shadow_bakeoff_retry_{stamp}.json", payload)
    base.write_json(LATEST, payload)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
