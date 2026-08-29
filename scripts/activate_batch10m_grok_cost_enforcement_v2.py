#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LIVE_ROOT = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS")
BACKEND = LIVE_ROOT / "BACK END" / "backend"
SOCIAL = BACKEND / "grok_social_intelligence.py"
ADAPTER = BACKEND / "grok_xai_sdk_adapter.py"
HELPER = BACKEND / "model_cost_enforcement.py"
REGISTRY = BACKEND / "grok_router_registry.py"
APP = BACKEND / "app.py"
COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.iios.model-cost-governor.plist"
LABEL = "com.iios.model-cost-governor"


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=check, timeout=timeout)


def git_modified(path: Path) -> bool:
    rel = path.relative_to(LIVE_ROOT)
    return run(["git", "diff", "--quiet", "HEAD", "--", str(rel)], cwd=LIVE_ROOT, check=False).returncode != 0


def social_binding_ready(source: str) -> bool:
    required = (
        "from model_cost_enforcement import preflight_xai_request",
        "MAX_X_SEARCH_ATTEMPTS = 1",
        '"cost_governor_binding": True',
        '"max_server_side_tool_calls_per_request": 3',
        '"prompt_cache_key_enabled": True',
        "record_xai_response(",
        '"max_tool_calls": 3',
        '"prompt_cache_key": "iios-grok-social-v1"',
    )
    return all(marker in source for marker in required)


def adapter_guard_ready(source: str) -> bool:
    return (
        "xai-official-sdk-citations-v5-cost-governor-aware" in source
        and "_xai_official_sdk_adapter_skipped_for_cost_governor" in source
        and 'plan.get("cost_governor_binding") is True' in source
    )


def app_router_ready(source: str) -> bool:
    return (
        "from grok_router_registry import install_grok_routers" in source
        and "install_grok_routers(app)" in source
    )


def patch_app(source: str) -> str:
    if app_router_ready(source):
        return source
    import_marker = "from governed_paper_execution_api import router as governed_paper_execution_router\n"
    include_marker = "app.include_router(semiconductor_router)\n"
    if import_marker not in source or include_marker not in source:
        raise RuntimeError("Expected app.py Grok wiring markers were not found")
    source = source.replace(
        import_marker,
        import_marker + "from grok_router_registry import install_grok_routers\n",
        1,
    )
    source = source.replace(
        include_marker,
        include_marker + "install_grok_routers(app)\n",
        1,
    )
    return source


def backup(path: Path, label: str) -> None:
    if not path.exists():
        return
    out = COST_DIR / "backups"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(path, out / f"{label}.{stamp}{path.suffix}")


def install_managed_file(source_path: Path, target_path: Path, *, guard, label: str) -> str:
    incoming = source_path.read_text(encoding="utf-8")
    current = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    if current and guard(current):
        return "PRESERVED_ALREADY_GOVERNED"
    if target_path.exists() and git_modified(target_path):
        raise RuntimeError(f"Refusing to overwrite locally modified {target_path.name}")
    backup(target_path, label)
    target_path.write_text(incoming, encoding="utf-8")
    if not guard(incoming):
        raise RuntimeError(f"Incoming {target_path.name} failed its governance marker check")
    return "INSTALLED"


def install_app_wiring() -> str:
    current = APP.read_text(encoding="utf-8")
    if app_router_ready(current):
        return "PRESERVED_ALREADY_WIRED"
    if git_modified(APP):
        raise RuntimeError("Refusing to patch app.py because it has local uncommitted changes")
    patched = patch_app(current)
    backup(APP, "app.pre-grok-router-wiring")
    APP.write_text(patched, encoding="utf-8")
    return "INSTALLED"


def install_cost_worker(python: str) -> None:
    COST_DIR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    if PLIST.exists():
        backup(PLIST, LABEL)
        run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], check=False, timeout=20)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [python, str(HELPER)],
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


def endpoint(path: str) -> dict[str, object]:
    result = run(["/usr/bin/curl", "-sS", "--max-time", "5", "-w", "\n%{http_code}", f"http://127.0.0.1:8002{path}"], check=False, timeout=10)
    lines = result.stdout.splitlines()
    code = lines[-1] if lines else "000"
    body = "\n".join(lines[:-1]) if len(lines) > 1 else ""
    payload: object = body
    try:
        payload = json.loads(body) if body else None
    except json.JSONDecodeError:
        pass
    return {"http_code": code, "payload": payload, "curl_returncode": result.returncode}


def main() -> int:
    parser = argparse.ArgumentParser(description="Finish binding Grok cost enforcement and register Grok routers safely.")
    parser.add_argument("--helper", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--registry", required=True)
    args = parser.parse_args()

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=LIVE_ROOT).stdout.strip()
    if branch != "experiment/grok-intelligence-v1":
        raise RuntimeError(f"Expected live checkout experiment/grok-intelligence-v1, found {branch}")

    helper_source = Path(args.helper).expanduser()
    adapter_source = Path(args.adapter).expanduser()
    registry_source = Path(args.registry).expanduser()
    for path in (helper_source, adapter_source, registry_source):
        if not path.exists():
            raise RuntimeError(f"Missing activation input: {path}")

    social_source = SOCIAL.read_text(encoding="utf-8")
    if not social_binding_ready(social_source):
        raise RuntimeError("Live grok_social_intelligence.py is not the verified binding-cost patch; refusing to continue")

    helper_action = install_managed_file(helper_source, HELPER, guard=lambda text: "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE" in text and "preflight_xai_request" in text, label="model_cost_enforcement")
    adapter_action = install_managed_file(adapter_source, ADAPTER, guard=adapter_guard_ready, label="grok_xai_sdk_adapter")
    registry_action = install_managed_file(registry_source, REGISTRY, guard=lambda text: "install_grok_routers" in text and "grok_social_intelligence" in text, label="grok_router_registry")
    app_action = install_app_wiring()

    python = sys.executable
    run([python, "-m", "py_compile", str(SOCIAL), str(ADAPTER), str(HELPER), str(REGISTRY), str(APP)], cwd=BACKEND, timeout=45)
    helper_run = run([python, str(HELPER)], cwd=BACKEND, timeout=30)
    install_cost_worker(python)

    before = backend_state()
    if before.get("auto_reload_detected"):
        time.sleep(5)

    plan = endpoint("/grok/experiment/plan")
    manifest = endpoint("/grok/experiment/manifest")
    binding_live = (
        plan.get("http_code") == "200"
        and isinstance(plan.get("payload"), dict)
        and plan["payload"].get("cost_governor_binding") is True
    )
    artifact_path = COST_DIR / "latest_model_cost_governor.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.exists() else {}

    output = {
        "status": "BATCH10M_GROK_COST_AND_ROUTER_WIRING_INSTALLED",
        "live_branch": branch,
        "social_binding_patch": "PRESERVED_VERIFIED",
        "helper_action": helper_action,
        "sdk_guard_action": adapter_action,
        "router_registry_action": registry_action,
        "app_router_wiring_action": app_action,
        "cost_governor_status": artifact.get("status"),
        "cost_budget_state": artifact.get("budget_state"),
        "enforcement_hooks_connected": artifact.get("enforcement_hooks_connected"),
        "backend_8002": before,
        "grok_plan": plan,
        "grok_manifest": manifest,
        "binding_hook_live_in_backend_8002": binding_live,
        "backend_restart_performed": False,
        "next_action": "NONE" if binding_live else "CONTROLLED_BACKEND_8002_RELOAD_REQUIRED",
        "broker_connected": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "helper_stdout": helper_run.stdout[-1200:],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
