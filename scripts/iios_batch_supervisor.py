#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "iios_batch_pipeline.json"
BACKEND_APP = REPO / "BACK END" / "backend" / "app.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Missing pipeline config: {CONFIG_PATH}")
    value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("Pipeline config must be a JSON object")
    return value


def state_dir(config: dict[str, Any]) -> Path:
    path = Path(
        os.path.expanduser(
            str(config.get("state_directory") or "~/.iios/batch-supervisor")
        )
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(config: dict[str, Any]) -> Path:
    return state_dir(config) / "state.json"


def latest_status_path(config: dict[str, Any]) -> Path:
    return state_dir(config) / "latest_status.json"


def log_path(config: dict[str, Any]) -> Path:
    return state_dir(config) / "supervisor.log"


def load_state(config: dict[str, Any]) -> dict[str, Any]:
    path = state_path(config)
    if not path.exists():
        return {
            "completed_batches": {},
            "last_head": None,
            "last_run_at": None,
            "last_error": None,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        value = {}
    if not isinstance(value, dict):
        value = {}
    value.setdefault("completed_batches", {})
    return value


def save_state(config: dict[str, Any], value: dict[str, Any]) -> None:
    state_path(config).write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def append_log(config: dict[str, Any], message: str) -> None:
    line = f"{utc_now()} {message}\n"
    with log_path(config).open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(message, flush=True)


class SupervisorLock:
    def __init__(self, config: dict[str, Any]):
        self.path = state_dir(config) / "supervisor.lock"
        self.handle = None

    def __enter__(self):
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another IIOS batch supervisor run is already active.")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path = REPO,
    timeout: int = 3600,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=capture,
        timeout=timeout,
    )


def current_branch() -> str:
    result = run_cmd(["git", "branch", "--show-current"])
    return result.stdout.strip() if result.returncode == 0 else ""


def current_head() -> str:
    result = run_cmd(["git", "rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""


def working_tree_status() -> str:
    result = run_cmd(["git", "status", "--porcelain"])
    return result.stdout if result.returncode == 0 else "<git status failed>"


def pull_ff_only(branch: str) -> tuple[bool, str]:
    result = run_cmd(["git", "pull", "--ff-only", "origin", branch], timeout=300)
    text = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, text


def safety_guard(config: dict[str, Any]) -> tuple[bool, list[str]]:
    if not BACKEND_APP.exists():
        return False, [f"Missing backend app: {BACKEND_APP}"]

    text = BACKEND_APP.read_text(encoding="utf-8")
    rules = config.get("safety_strings") or {}
    required = [str(x) for x in rules.get("required_present") or []]
    forbidden = [str(x) for x in rules.get("forbidden_present") or []]

    errors: list[str] = []
    for item in required:
        if item not in text:
            errors.append(f"Required safety invariant not found in app.py: {item}")
    for item in forbidden:
        if item in text:
            errors.append(f"Forbidden safety invariant found in app.py: {item}")
    return not errors, errors


def json_path(value: Any, dotted: str) -> Any:
    current = value
    for part in dotted.split("."):
        if not part:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def get_json(url: str, timeout: int = 4) -> tuple[bool, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return True, json.loads(raw) if raw else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_external_gates(config: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for gate in config.get("external_gates") or []:
        if not isinstance(gate, dict):
            continue
        result = {
            "id": gate.get("id"),
            "name": gate.get("name"),
            "blocks_engineering_lane": bool(gate.get("blocks_engineering_lane")),
            "human_gate": bool(gate.get("human_gate")),
            "issue_number": gate.get("issue_number"),
            "ready": None,
            "status": "HUMAN_GATE" if gate.get("human_gate") else "UNKNOWN",
        }
        endpoint = str(gate.get("status_endpoint") or "").strip()
        if endpoint:
            ok, payload = get_json(endpoint)
            if ok:
                ready = bool(json_path(payload, str(gate.get("ready_json_path") or "")))
                result["ready"] = ready
                result["status"] = "READY" if ready else "PENDING"
            else:
                result["status"] = "BACKEND_UNREACHABLE"
                result["error"] = str(payload)
        output.append(result)
    return output


def dependencies_complete(batch: dict[str, Any], completed: dict[str, Any]) -> bool:
    deps = [str(x) for x in batch.get("depends_on") or []]
    return all(dep in completed for dep in deps)


def run_apply_script(
    config: dict[str, Any],
    batch: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    script = REPO / str(batch.get("apply_script") or "")
    before = current_head()
    started = utc_now()

    append_log(config, f"AUTO-RUN {batch.get('id')}: {script.relative_to(REPO)}")
    result = run_cmd(
        [sys.executable, str(script)],
        timeout=60 * 60 * 3,
        capture=True,
    )
    after = current_head()

    stdout_tail = (result.stdout or "")[-12000:]
    stderr_tail = (result.stderr or "")[-12000:]
    detail = {
        "id": batch.get("id"),
        "name": batch.get("name"),
        "script": str(script.relative_to(REPO)),
        "started_at": started,
        "finished_at": utc_now(),
        "returncode": result.returncode,
        "head_before": before,
        "head_after": after,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    return result.returncode == 0, detail


def run_once(config: dict[str, Any]) -> dict[str, Any]:
    state = load_state(config)
    branch = str(config.get("branch") or "feature/batch8-paper-portfolio")
    summary: dict[str, Any] = {
        "run_at": utc_now(),
        "branch": branch,
        "repo": str(REPO),
        "actions": [],
        "attention_required": [],
        "engineering_lane": [],
        "external_gates": [],
    }

    actual_branch = current_branch()
    summary["actual_branch"] = actual_branch
    if actual_branch != branch:
        reason = f"Wrong branch: expected {branch}, found {actual_branch or '<detached>'}"
        summary["attention_required"].append(reason)
        state["last_error"] = reason
        state["last_run_at"] = summary["run_at"]
        save_state(config, state)
        return summary

    dirty = working_tree_status()
    if dirty.strip():
        reason = "Working tree is not clean; supervisor will not stash, reset, or overwrite local work."
        summary["attention_required"].append(reason)
        summary["dirty_status"] = dirty
        state["last_error"] = reason
        state["last_run_at"] = summary["run_at"]
        save_state(config, state)
        return summary

    safe, safety_errors = safety_guard(config)
    summary["safety_ok_before_pull"] = safe
    if not safe:
        summary["attention_required"].extend(safety_errors)
        state["last_error"] = "; ".join(safety_errors)
        state["last_run_at"] = summary["run_at"]
        save_state(config, state)
        return summary

    pulled, pull_text = pull_ff_only(branch)
    summary["pull"] = {"ok": pulled, "detail": pull_text[-4000:]}
    if not pulled:
        reason = "git pull --ff-only failed; merge/conflict or remote access needs human review."
        summary["attention_required"].append(reason)
        state["last_error"] = reason
        state["last_run_at"] = summary["run_at"]
        save_state(config, state)
        return summary

    safe, safety_errors = safety_guard(config)
    summary["safety_ok_after_pull"] = safe
    if not safe:
        summary["attention_required"].extend(safety_errors)
        state["last_error"] = "; ".join(safety_errors)
        state["last_run_at"] = summary["run_at"]
        save_state(config, state)
        return summary

    external = check_external_gates(config)
    summary["external_gates"] = external

    blocking_pending = [
        gate
        for gate in external
        if gate.get("blocks_engineering_lane") and gate.get("ready") is not True
    ]

    completed = state.setdefault("completed_batches", {})
    engineering = config.get("engineering_lane") or []

    for batch in engineering:
        if not isinstance(batch, dict):
            continue
        batch_id = str(batch.get("id") or "")
        row = {
            "id": batch_id,
            "name": batch.get("name"),
            "apply_script": batch.get("apply_script"),
        }

        if batch_id in completed:
            row["status"] = "COMPLETE"
            row["completed"] = completed[batch_id]
            summary["engineering_lane"].append(row)
            continue

        if not dependencies_complete(batch, completed):
            row["status"] = "WAITING_FOR_DEPENDENCY"
            row["depends_on"] = batch.get("depends_on") or []
            summary["engineering_lane"].append(row)
            continue

        if blocking_pending and not bool(batch.get("parallel_with_external_gates")):
            row["status"] = "WAITING_FOR_EXTERNAL_GATE"
            summary["engineering_lane"].append(row)
            continue

        script = REPO / str(batch.get("apply_script") or "")
        if not script.exists():
            row["status"] = "WAITING_FOR_REVIEWED_APPLY_ARTIFACT"
            summary["engineering_lane"].append(row)
            continue

        dirty = working_tree_status()
        if dirty.strip():
            reason = f"Tree became dirty before {batch_id}; refusing automatic apply."
            row["status"] = "HUMAN_REVIEW_REQUIRED"
            summary["engineering_lane"].append(row)
            summary["attention_required"].append(reason)
            break

        ok, detail = run_apply_script(config, batch)
        summary["actions"].append(detail)
        if not ok:
            row["status"] = "FAILED_APPLY"
            row["returncode"] = detail.get("returncode")
            summary["engineering_lane"].append(row)
            summary["attention_required"].append(
                f"{batch_id} apply failed with return code {detail.get('returncode')}."
            )
            break

        safe_after, after_errors = safety_guard(config)
        if not safe_after:
            row["status"] = "SAFETY_REVIEW_REQUIRED"
            summary["engineering_lane"].append(row)
            summary["attention_required"].extend(after_errors)
            break

        completed[batch_id] = {
            "completed_at": utc_now(),
            "head": current_head(),
            "script": str(script.relative_to(REPO)),
        }
        row["status"] = "COMPLETE_THIS_RUN"
        row["completed"] = completed[batch_id]
        summary["engineering_lane"].append(row)
        append_log(config, f"COMPLETE {batch_id}: head {current_head()[:12]}")

        # Pull again because apply scripts are expected to commit/push and later
        # batches may have landed while this one was running.
        if not working_tree_status().strip():
            pull_ff_only(branch)

    state["last_head"] = current_head()
    state["last_run_at"] = summary["run_at"]
    state["last_error"] = summary["attention_required"] or None
    save_state(config, state)
    latest_status_path(config).write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return summary


def print_summary(summary: dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print("IIOS AUTONOMOUS BATCH SUPERVISOR")
    print("=" * 72)
    print("Branch:", summary.get("actual_branch") or summary.get("branch"))
    print("Head actions:", len(summary.get("actions") or []))

    print("\nEXTERNAL / HUMAN GATES")
    for gate in summary.get("external_gates") or []:
        print(
            " ",
            gate.get("id"),
            "-",
            gate.get("status"),
            "-",
            gate.get("name"),
        )

    print("\nENGINEERING LANE")
    for batch in summary.get("engineering_lane") or []:
        print(" ", batch.get("id"), "-", batch.get("status"), "-", batch.get("name"))

    attention = summary.get("attention_required") or []
    print("\nHUMAN ATTENTION:", "YES" if attention else "NO")
    for item in attention:
        print("  -", item)
    print("=" * 72)


def status_only(config: dict[str, Any]) -> int:
    path = latest_status_path(config)
    if not path.exists():
        print("No supervisor status has been recorded yet.")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS autonomous gated batch supervisor")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one supervisor cycle (default)")
    mode.add_argument("--loop", action="store_true", help="Run continuously in this terminal")
    mode.add_argument("--status", action="store_true", help="Print the latest recorded supervisor status")
    args = parser.parse_args()

    config = load_config()
    if args.status:
        return status_only(config)

    poll = max(60, int(config.get("poll_seconds") or 900))

    if args.loop:
        while True:
            try:
                with SupervisorLock(config):
                    summary = run_once(config)
                    print_summary(summary)
            except SystemExit as exc:
                print(str(exc), flush=True)
            except Exception as exc:
                append_log(config, f"SUPERVISOR ERROR: {type(exc).__name__}: {exc}")
            time.sleep(poll)

    with SupervisorLock(config):
        summary = run_once(config)
        print_summary(summary)
    return 2 if summary.get("attention_required") else 0


if __name__ == "__main__":
    raise SystemExit(main())
