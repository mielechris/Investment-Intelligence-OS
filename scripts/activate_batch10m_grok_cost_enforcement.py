#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LIVE_ROOT = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS")
BACKEND = LIVE_ROOT / "BACK END" / "backend"
TARGET = BACKEND / "grok_social_intelligence.py"
HELPER_TARGET = BACKEND / "model_cost_enforcement.py"
COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.iios.model-cost-governor.plist"
LABEL = "com.iios.model-cost-governor"


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=check, timeout=timeout)


def git_modified(path: Path) -> bool:
    rel = path.relative_to(LIVE_ROOT)
    result = run(["git", "diff", "--quiet", "HEAD", "--", str(rel)], cwd=LIVE_ROOT, check=False)
    return result.returncode != 0


def patch_source(source: str) -> str:
    if "from model_cost_enforcement import preflight_xai_request" not in source:
        if "import threading\n" not in source:
            raise RuntimeError("Expected threading import marker not found")
        source = source.replace("import threading\n", "import threading\nimport time\n", 1)
        marker = "from ledger import get_object, latest_object, record_event, record_object, utc_now\n"
        if marker not in source:
            raise RuntimeError("Expected ledger import marker not found")
        source = source.replace(
            marker,
            marker + "from model_cost_enforcement import preflight_xai_request, record_xai_failure, record_xai_response, register_hook\n",
            1,
        )

    source = source.replace("MAX_X_SEARCH_ATTEMPTS = 2", "MAX_X_SEARCH_ATTEMPTS = 1", 1)

    plan_marker = '        "max_x_search_attempts": MAX_X_SEARCH_ATTEMPTS,\n'
    if '"cost_governor_binding": True' not in source:
        if plan_marker not in source:
            raise RuntimeError("Expected Grok plan marker not found")
        source = source.replace(
            plan_marker,
            plan_marker
            + '        "cost_governor_binding": True,\n'
            + '        "cost_governor_policy": "batch10m-grok-cost-enforcement-v1",\n'
            + '        "max_server_side_tool_calls_per_request": 3,\n'
            + '        "prompt_cache_key_enabled": True,\n',
            1,
        )

    usage_pattern = re.compile(
        r"def _usage_summary\(response: Any\) -> dict\[str, Any\]:\n.*?\n\ndef _contains_prompt_injection",
        re.S,
    )
    usage_replacement = '''def _usage_summary(response: Any) -> dict[str, Any]:
    dump = _response_dump(response)
    usage = dump.get("usage") if isinstance(dump.get("usage"), dict) else {}
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    try:
        cost_ticks = int(usage.get("cost_in_usd_ticks") or 0)
    except (TypeError, ValueError):
        cost_ticks = 0
    exact_cost = round(cost_ticks / 1e10, 8) if cost_ticks else None
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cached_input_tokens": int(details.get("cached_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "server_side_tools_used": usage.get("num_server_side_tools_used"),
        "cost_in_usd_ticks": cost_ticks,
        "exact_cost_usd": exact_cost,
        "cost_is_provider_reported_exact": exact_cost is not None,
        "estimated_cost_usd": exact_cost,
        "estimated_cost_usd_note": "BACKWARD_COMPATIBILITY_ALIAS_OF_PROVIDER_REPORTED_EXACT_COST",
    }


def _contains_prompt_injection'''
    source, usage_count = usage_pattern.subn(usage_replacement, source, count=1)
    if usage_count != 1:
        raise RuntimeError("Could not replace Grok usage summary")

    run_pattern = re.compile(
        r"def _run_x_search\(client: OpenAI, \*, prompt: str, from_date: str, to_date: str\) -> tuple\[Any, int\]:\n.*?\n\ndef fetch_grok_social_context",
        re.S,
    )
    run_replacement = '''def _run_x_search(
    client: OpenAI,
    *,
    prompt: str,
    from_date: str,
    to_date: str,
    case_id: str | None = None,
    query_label: str | None = None,
) -> tuple[Any, int]:
    last_error: Exception | None = None
    query_value = query_label or prompt
    estimated_input_tokens = max(1, (len(prompt) + 3) // 4)
    for attempt in range(1, MAX_X_SEARCH_ATTEMPTS + 1):
        admission = preflight_xai_request(
            query=query_value,
            model=grok_model(),
            case_id=case_id,
            estimated_input_tokens=estimated_input_tokens,
        )
        if admission.get("allow") is not True:
            reason = ",".join(str(value) for value in admission.get("reasons") or [])
            raise RuntimeError(f"GROK_COST_GOVERNOR_{admission.get('decision')}: {reason}"[:1000])
        started = time.monotonic()
        try:
            response = client.responses.create(
                model=grok_model(),
                input=prompt,
                tools=[{"type": "x_search", "from_date": from_date, "to_date": to_date}],
                max_output_tokens=2000,
                extra_body={
                    "prompt_cache_key": "iios-grok-social-v1",
                    "max_tool_calls": 3,
                },
            )
            record_xai_response(
                response,
                model=grok_model(),
                query=query_value,
                case_id=case_id,
                latency_ms=(time.monotonic() - started) * 1000.0,
            )
            return response, attempt
        except APITimeoutError as exc:
            record_xai_failure(
                model=grok_model(),
                query=query_value,
                case_id=case_id,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_type="APITimeoutError",
            )
            last_error = exc
            if attempt >= MAX_X_SEARCH_ATTEMPTS:
                raise
        except Exception as exc:
            record_xai_failure(
                model=grok_model(),
                query=query_value,
                case_id=case_id,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error_type=type(exc).__name__,
            )
            raise
    raise last_error or RuntimeError("Grok X Search failed")


def fetch_grok_social_context'''
    source, run_count = run_pattern.subn(run_replacement, source, count=1)
    if run_count != 1:
        if "GROK_COST_GOVERNOR_" not in source:
            raise RuntimeError("Could not replace Grok X Search boundary")

    old_call = "response, api_attempts = _run_x_search(client, prompt=prompt, from_date=from_date, to_date=to_date)"
    new_call = "response, api_attempts = _run_x_search(client, prompt=prompt, from_date=from_date, to_date=to_date, case_id=ticker, query_label=subject)"
    if old_call in source:
        source = source.replace(old_call, new_call, 1)
    elif new_call not in source:
        raise RuntimeError("Expected Grok X Search call marker not found")

    return source


def install_cost_worker(python: str) -> None:
    COST_DIR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = COST_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if PLIST.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(PLIST, backup_dir / f"{LABEL}.{stamp}.plist")
        run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], check=False, timeout=20)

    payload = {
        "Label": LABEL,
        "ProgramArguments": [python, str(HELPER_TARGET)],
        "WorkingDirectory": str(BACKEND),
        "RunAtLoad": True,
        "StartInterval": 300,
        "StandardOutPath": str(COST_DIR / "model-cost-governor.out.log"),
        "StandardErrorPath": str(COST_DIR / "model-cost-governor.err.log"),
        "EnvironmentVariables": {"PYTHONPATH": str(BACKEND)},
    }
    with PLIST.open("wb") as handle:
        plistlib.dump(payload, handle)
    run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(PLIST)], timeout=20)
    run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LABEL}"], check=False, timeout=20)


def backend_state() -> dict[str, object]:
    pids = run(["/usr/sbin/lsof", "-tiTCP:8002", "-sTCP:LISTEN"], check=False, timeout=10).stdout.split()
    rows = []
    for pid in pids:
        command = run(["ps", "-p", pid, "-o", "command="], check=False, timeout=10).stdout.strip()
        rows.append({"pid": int(pid), "command": command, "auto_reload": "--reload" in command})
    return {"listeners": rows, "auto_reload_detected": any(bool(row["auto_reload"]) for row in rows)}


def plan_reports_binding() -> bool:
    try:
        result = run(["/usr/bin/curl", "-fsS", "--max-time", "5", "http://127.0.0.1:8002/grok/experiment/plan"], check=False, timeout=10)
        payload = json.loads(result.stdout) if result.returncode == 0 and result.stdout else {}
        return payload.get("cost_governor_binding") is True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Activate binding IIOS Grok cost enforcement without changing Backend 8002 authority.")
    parser.add_argument("--helper", required=True)
    args = parser.parse_args()
    helper_source = Path(args.helper).expanduser()
    if not helper_source.exists():
        raise RuntimeError(f"Missing helper file: {helper_source}")
    if not TARGET.exists():
        raise RuntimeError(f"Missing live Grok source: {TARGET}")
    if git_modified(TARGET):
        raise RuntimeError("Refusing to patch grok_social_intelligence.py because it has local uncommitted changes")

    original = TARGET.read_text(encoding="utf-8")
    patched = patch_source(original)
    COST_DIR.mkdir(parents=True, exist_ok=True)
    backup = COST_DIR / "backups" / "grok_social_intelligence.pre-cost-enforcement.py"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")

    HELPER_TARGET.write_text(helper_source.read_text(encoding="utf-8"), encoding="utf-8")
    TARGET.write_text(patched, encoding="utf-8")

    python = sys.executable
    run([python, "-m", "py_compile", str(HELPER_TARGET), str(TARGET)], cwd=BACKEND, timeout=30)
    hook_result = run([python, str(HELPER_TARGET)], cwd=BACKEND, timeout=30)
    install_cost_worker(python)

    before = backend_state()
    if before.get("auto_reload_detected"):
        time.sleep(4)
    binding_live = plan_reports_binding()
    artifact_path = COST_DIR / "latest_model_cost_governor.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.exists() else {}

    output = {
        "status": "BATCH10M_GROK_COST_ENFORCEMENT_PATCHED",
        "source_branch_expected": "experiment/grok-intelligence-v1",
        "live_source_patched": True,
        "grok_max_api_attempts": 1,
        "max_server_side_tool_calls_per_request": 3,
        "max_output_tokens": 2000,
        "prompt_cache_key": "iios-grok-social-v1",
        "duplicate_query_ttl_seconds": 1800,
        "daily_soft_limit_usd": 10.0,
        "daily_hard_limit_usd": 20.0,
        "rolling_7d_soft_limit_usd": 50.0,
        "rolling_7d_hard_limit_usd": 75.0,
        "cost_worker": LABEL,
        "cost_governor_status": artifact.get("status"),
        "cost_budget_state": artifact.get("budget_state"),
        "enforcement_hooks_connected": artifact.get("enforcement_hooks_connected"),
        "backend_8002_listeners": before.get("listeners"),
        "backend_auto_reload_detected": before.get("auto_reload_detected"),
        "binding_hook_live_in_backend_8002": binding_live,
        "backend_restart_performed": False,
        "next_action": "NONE" if binding_live else "CONTROLLED_BACKEND_RELOAD_REQUIRED_FOR_IN_MEMORY_GROK_MODULE",
        "broker_connected": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "helper_stdout": hook_result.stdout[-1000:],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
