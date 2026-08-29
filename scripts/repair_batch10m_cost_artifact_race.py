#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

LIVE_ROOT = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10l-10m-measurement-health-superbatch")
BRANCH = "feature/batch10l-10m-measurement-health-superbatch"
COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"
ARTIFACT = COST_DIR / "latest_model_cost_governor.json"
HOOKS = COST_DIR / "enforcement_hooks.json"
LIVE_HELPER = LIVE_ROOT / "BACK END" / "backend" / "model_cost_enforcement.py"
FINAL_LABEL = "com.iios.institutional-browser-artifacts"
COST_LABEL = "com.iios.model-cost-governor"
LAUNCH_DIR = Path.home() / "Library" / "LaunchAgents"


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=False, timeout=timeout)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args[:8])}\n{detail[:3000]}")
    return result


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def hook_connected() -> bool:
    registry = load_json(HOOKS)
    hooks = registry.get("hooks") if isinstance(registry.get("hooks"), dict) else {}
    grok = hooks.get("xai_grok_social_intelligence") if isinstance(hooks.get("xai_grok_social_intelligence"), dict) else {}
    return grok.get("connected") is True and grok.get("binding") is True


def worktree_safe() -> None:
    if not WORKTREE.exists():
        raise RuntimeError(f"Missing 10L-10M worktree: {WORKTREE}")
    status = run(["git", "status", "--porcelain"], cwd=WORKTREE).stdout.splitlines()
    allowed = ("FRONT END/dist/", "scripts/__pycache__/")
    unexpected = []
    for line in status:
        path = line[3:].strip().strip('"') if len(line) >= 4 else ""
        if path and not any(path.startswith(prefix) for prefix in allowed):
            unexpected.append(line)
    if unexpected:
        raise RuntimeError("10L-10M worktree has non-generated local changes; refusing reset:\n" + "\n".join(unexpected[:20]))


def plist_program(label: str) -> list[str]:
    path = LAUNCH_DIR / f"{label}.plist"
    if not path.exists():
        return []
    try:
        with path.open("rb") as handle:
            payload = plistlib.load(handle)
    except Exception:
        return []
    values = payload.get("ProgramArguments")
    return [str(v) for v in values] if isinstance(values, list) else []


def assert_enforcement(stage: str) -> dict:
    artifact = load_json(ARTIFACT)
    if artifact.get("status") != "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE":
        raise RuntimeError(f"{stage}: cost artifact downgraded to {artifact.get('status')}")
    if artifact.get("enforcement_hooks_connected") is not True or artifact.get("binding_xai_grok_hook") is not True:
        raise RuntimeError(f"{stage}: binding hook flags are not true")
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), dict) else {}
    for key in ("capital_authority", "trade_execution_permission", "live_execution"):
        if safety.get(key) is not False:
            raise RuntimeError(f"{stage}: safety invariant failed: {key}")
    return artifact


def main() -> int:
    if sys.platform != "darwin":
        raise RuntimeError("This repair is macOS-only")
    if not hook_connected():
        raise RuntimeError("Binding Grok hook registry is not connected; refusing artifact-race repair")
    if not LIVE_HELPER.exists():
        raise RuntimeError(f"Missing live binding helper: {LIVE_HELPER}")

    worktree_safe()
    run(["git", "fetch", "origin", BRANCH], cwd=WORKTREE)
    run(["git", "reset", "--hard", f"origin/{BRANCH}"], cwd=WORKTREE)

    governor = WORKTREE / "scripts" / "iios_model_cost_governor.py"
    text = governor.read_text(encoding="utf-8")
    if "_binding_hook_connected" not in text or "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE" not in text:
        raise RuntimeError("Fetched 10L-10M governor does not contain binding-artifact preservation fix")

    backend = LIVE_ROOT / "BACK END" / "backend"
    helper_run = run([sys.executable, str(LIVE_HELPER)], cwd=backend, timeout=45)
    before = assert_enforcement("after live helper republish")

    fixed_run = run([sys.executable, str(governor), "--cost-dir", str(COST_DIR)], cwd=WORKTREE, timeout=45)
    after_fixed_governor = assert_enforcement("after fixed 10L-10M governor")

    domain = f"gui/{os.getuid()}"
    final_plist = LAUNCH_DIR / f"{FINAL_LABEL}.plist"
    if final_plist.exists():
        run(["launchctl", "kickstart", "-k", f"{domain}/{FINAL_LABEL}"], check=False, timeout=20)
        time.sleep(4)
    after_publisher = assert_enforcement("after 10L-10M browser publisher")

    cost_program = plist_program(COST_LABEL)
    final_program = plist_program(FINAL_LABEL)
    output = {
        "status": "BATCH10M_COST_ARTIFACT_RACE_REPAIRED",
        "binding_hook_registry_connected": True,
        "worktree_synced_to": BRANCH,
        "cost_governor_status": after_publisher.get("status"),
        "cost_budget_state": after_publisher.get("budget_state"),
        "enforcement_hooks_connected": after_publisher.get("enforcement_hooks_connected"),
        "binding_xai_grok_hook": after_publisher.get("binding_xai_grok_hook"),
        "artifact_survived_fixed_governor": after_fixed_governor.get("status") == "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE",
        "artifact_survived_browser_publisher": after_publisher.get("status") == "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE",
        "cost_worker_program": cost_program,
        "browser_publisher_program": final_program,
        "backend_8002_started_by_this_repair": False,
        "next_action": "START_BACKEND_8002_AND_VERIFY_GROK_ROUTES",
        "broker_connected": False,
        "capital_authority": False,
        "trade_execution_permission": False,
        "live_execution": False,
        "helper_stdout": helper_run.stdout[-1000:],
        "fixed_governor_stdout": fixed_run.stdout[-1000:],
        "prior_exact_spend_usd": (before.get("rolling_7d") or {}).get("exact_spend_usd"),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
