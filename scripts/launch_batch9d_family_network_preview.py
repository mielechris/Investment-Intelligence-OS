#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9d-family-network-preview")
BRANCH = "feature/batch9d-live-agent-cortex"
LEDGER = LIVE / "BACK END" / "backend" / "iios_ledger.db"
DOTENV = LIVE / "BACK END" / "backend" / ".env"
BACKEND_PORT = 8005
FRONTEND_PORT = 5191
PREVIEW_URL = f"http://127.0.0.1:{FRONTEND_PORT}"
API_URL = f"http://127.0.0.1:{BACKEND_PORT}"

VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)

NODE_MODULE_CANDIDATES = (
    LIVE / "FRONT END" / "node_modules",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/FRONT END/node_modules"),
)


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=check,
    )


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
    ).strip()


def load_dotenv(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, posix=True)
            env[key] = parsed[0] if len(parsed) == 1 else value.strip('"\'')
        except ValueError:
            env[key] = value.strip('"\'')


def resolve_python() -> Path:
    for candidate in VENV_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found; refusing system Python fallback")


def port_is_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def wait_http(url: str, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def prepare_node_modules(frontend: Path) -> None:
    target = frontend / "node_modules"
    if target.exists() or target.is_symlink():
        return
    for candidate in NODE_MODULE_CANDIDATES:
        if candidate.exists():
            target.symlink_to(candidate, target_is_directory=True)
            print(f"Frontend dependencies: linked from {candidate}")
            return
    print("No reusable frontend node_modules found; running npm ci in preview worktree...")
    run("npm", "ci", cwd=frontend)


def terminate(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live Batch8 checkout not found: {LIVE}")
    if not LEDGER.exists():
        raise SystemExit(f"Live governed ledger not found: {LEDGER}")
    if not port_is_free(BACKEND_PORT):
        raise SystemExit(
            f"Preview API port {BACKEND_PORT} is already in use. Refusing to stop another process."
        )
    if not port_is_free(FRONTEND_PORT):
        raise SystemExit(
            f"Preview UI port {FRONTEND_PORT} is already in use. Refusing to stop another process."
        )

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9D — ISOLATED FAMILY NETWORK PREVIEW")
    print(f"Live checkout: {LIVE}")
    print(f"Live branch: {branch_before}")
    print(f"Governed ledger: {LEDGER}")
    print("Live Batch8 working-tree mutation: FORBIDDEN")
    print("Existing 5175 / 5190 / 8002 / 9A / 9B processes: UNTOUCHED")
    print("Preview API: READ-ONLY GET SURFACE ONLY")
    print("Family Network motion: LEDGER-BOUND")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)

    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"Preview path exists but is not a git worktree: {WORKTREE}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)
        run("git", "clean", "-fd", cwd=WORKTREE)
    else:
        run(
            "git",
            "worktree",
            "add",
            "--detach",
            str(WORKTREE),
            f"origin/{BRANCH}",
            cwd=LIVE,
        )

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    if branch_after != branch_before or status_after != status_before:
        raise SystemExit("Refusing preview: live Batch8 branch or tracked working tree changed")

    frontend = WORKTREE / "FRONT END"
    prepare_node_modules(frontend)

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["IIOS_DB_PATH"] = str(LEDGER)
    env["PYTHONUNBUFFERED"] = "1"

    frontend_env = dict(env)
    frontend_env["VITE_IIOS_API_URL"] = API_URL

    api_process: subprocess.Popen[str] | None = None
    ui_process: subprocess.Popen[str] | None = None

    try:
        print(f"Starting read-only 9D preview API on {API_URL} ...")
        api_process = subprocess.Popen(
            [
                str(python),
                "-m",
                "uvicorn",
                "batch9d_preview_api:app",
                "--app-dir",
                "scripts",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(WORKTREE),
            env=env,
            text=True,
        )
        wait_http(f"{API_URL}/health")
        print("Read-only 9D preview API: READY")

        vite = frontend / "node_modules" / ".bin" / "vite"
        if not vite.exists():
            raise RuntimeError(f"Vite executable not found: {vite}")

        print(f"Starting Family Network browser preview on {PREVIEW_URL} ...")
        ui_process = subprocess.Popen(
            [
                str(vite),
                "--host",
                "127.0.0.1",
                "--port",
                str(FRONTEND_PORT),
                "--strictPort",
            ],
            cwd=str(frontend),
            env=frontend_env,
            text=True,
        )
        wait_http(PREVIEW_URL)

        print("\n=== BATCH 9D FAMILY NETWORK PREVIEW READY ===")
        print(f"Browser: {PREVIEW_URL}")
        print("Cortex motor: ONLINE heartbeat from 9A/9B cadence")
        print("Bright signal packets: ONLY from recent governed ledger events")
        print("API authority: READ-ONLY")
        print("Live ledger: SHARED FOR OBSERVATION ONLY")
        print("Existing IIOS processes: UNTOUCHED")
        print("Use Ctrl+C in THIS preview terminal only when you want to stop the preview.")

        if sys.platform == "darwin":
            subprocess.Popen(["open", PREVIEW_URL])

        while True:
            if api_process.poll() is not None:
                raise RuntimeError(
                    f"Preview API exited unexpectedly with code {api_process.returncode}"
                )
            if ui_process.poll() is not None:
                raise RuntimeError(
                    f"Preview UI exited unexpectedly with code {ui_process.returncode}"
                )
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping Batch 9D Family Network preview only...")
        return 0
    finally:
        terminate(ui_process)
        terminate(api_process)
        print("Batch 9D preview stopped. Live IIOS lanes were not stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
