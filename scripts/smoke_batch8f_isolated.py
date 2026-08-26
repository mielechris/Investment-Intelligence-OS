#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import smoke_batch8f_live as smoke

PORT = int(os.environ.get("IIOS_INTEGRATION_SMOKE_PORT", "8102"))
if PORT == 8002:
    raise SystemExit("STOP: isolated integration smoke may not use operator port 8002.")

smoke.BASE = f"http://127.0.0.1:{PORT}"
smoke.LOG = Path(f"/tmp/iios_backend_{PORT}_v019_integration.log")
smoke.REPORT = Path(f"/tmp/iios_batch8f_integration_smoke_{PORT}.json")


def listening_pids() -> list[int]:
    if shutil.which("lsof") is None:
        return []
    result = subprocess.run(
        ["lsof", f"-tiTCP:{PORT}", "-sTCP:LISTEN"],
        text=True,
        capture_output=True,
        check=False,
    )
    return [int(value) for value in result.stdout.split() if value.isdigit()]


def kill_smoke_port() -> None:
    pids = listening_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        if not listening_pids():
            return
        time.sleep(0.25)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_backend():
    smoke.LOG.write_text("")
    log = smoke.LOG.open("ab", buffering=0)
    py = str(smoke.PYTHON if smoke.PYTHON.exists() else Path(sys.executable))
    try:
        proc = subprocess.Popen(
            [
                py,
                "-m",
                "uvicorn",
                "app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--lifespan",
                "off",
            ],
            cwd=smoke.BACKEND,
            env=smoke.env(),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log.close()

    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            break
        last = smoke.call("/system/status", timeout=2)
        if last["ok"] and (last["data"] or {}).get("version") == "0.19.0":
            return proc, last["data"]
        time.sleep(0.5)

    exit_code = proc.poll()
    smoke.stop_backend(proc)
    try:
        log_text = smoke.LOG.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log_text = f"Unable to read backend log: {exc}"
    raise RuntimeError(
        "v0.19.0 isolated backend did not become ready. "
        f"port={PORT}; exit_code={exit_code}; last={last}; "
        f"log={smoke.LOG}\n--- backend log ---\n{log_text}"
    )


smoke.listening_pids = listening_pids
smoke.kill_8002 = kill_smoke_port
smoke.start_backend = start_backend

print(f"ISOLATED INTEGRATION MODE: Batch 8F smoke backend will use port {PORT}; operator port 8002 is untouched.")
raise SystemExit(smoke.main())
