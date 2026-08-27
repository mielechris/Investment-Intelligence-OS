#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

LIVE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-Batch8")
WORKTREE = Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9e-radar")
BRANCH = "feature/batch9e-high-speed-market-radar"
DOTENV = LIVE / "BACK END" / "backend" / ".env"

VENV_CANDIDATES = (
    LIVE / "BACK END" / "backend" / ".venv" / "bin" / "python",
    Path("/Users/crm/Documents/GitHub/Investment-Intelligence-OS/BACK END/backend/.venv/bin/python"),
)


def run(*args: str, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None):
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        text=True,
        check=check,
        env=env,
    )


def capture(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(list(args), cwd=str(cwd) if cwd else None, text=True).strip()


def resolve_python() -> Path:
    for candidate in VENV_CANDIDATES:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("No IIOS backend virtualenv Python found; refusing system Python fallback")


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
            env[key] = parsed[0] if len(parsed) == 1 else value.strip("\"'")
        except ValueError:
            env[key] = value.strip("\"'")


def main() -> int:
    if not LIVE.exists():
        raise SystemExit(f"Live checkout not found: {LIVE}")

    branch_before = capture("git", "branch", "--show-current", cwd=LIVE)
    status_before = capture("git", "status", "--porcelain", cwd=LIVE)

    print("IIOS BATCH 9E — OFFICIAL INDEX UNIVERSE ACCEPTANCE")
    print("Objective: verify production S&P 500 + Nasdaq-100 official-source membership")
    print("Acceptance-only screener fallback: FORBIDDEN")
    print("Model calls: DISABLED")
    print("Case promotions: DISABLED")
    print("8-agent case floor: DISABLED")
    print("Paper order authority: FALSE")
    print("Broker connected: FALSE")
    print("Live execution: FALSE")

    run("git", "fetch", "origin", BRANCH, cwd=LIVE)
    if WORKTREE.exists():
        if not (WORKTREE / ".git").exists():
            raise SystemExit(f"9E path exists but is not a git worktree: {WORKTREE}")
        run("git", "reset", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)
        run("git", "clean", "-fd", cwd=WORKTREE)
    else:
        run("git", "worktree", "add", "--detach", str(WORKTREE), f"origin/{BRANCH}", cwd=LIVE)

    python = resolve_python()
    env = dict(os.environ)
    load_dotenv(DOTENV, env)
    env["PYTHONUNBUFFERED"] = "1"

    code = r'''
import sys
from pathlib import Path

root = Path.cwd()
backend = root / "BACK END" / "backend"
sys.path.insert(0, str(backend))

from index_tls_bootstrap import configure_verified_tls
import production_index_universe

print("\n=== VERIFIED TLS PRECHECK ===")
tls = configure_verified_tls()
print(f"TLS configured: {tls.get('configured') is True}")
print(f"TLS mode: {tls.get('mode')}")
print(f"Certificate verification: {tls.get('certificate_verification') is True}")
print(f"Hostname verification: {tls.get('hostname_verification') is True}")

print("\n=== OFFICIAL INDEX REFRESH ===")
result = production_index_universe.refresh_official_index_universe()
indexes = result.get("indexes") or {}
sp = indexes.get("SP500") or {}
ndx = indexes.get("NASDAQ100") or {}

for label, row in (("SP500", sp), ("NASDAQ100", ndx)):
    print(
        f"{label}: verified={row.get('verified_complete')} "
        f"count={row.get('symbol_count')} "
        f"mode={row.get('source_mode')} "
        f"source={row.get('source_ref')} "
        f"error={row.get('error')}"
    )

merged_count = int(result.get("symbol_count") or 0)
print(f"Merged universe verified: {result.get('verified_complete') is True}")
print(f"Strict membership: {result.get('strict_membership') is True}")
print(f"Merged unique symbols: {merged_count}")
print(f"Fail closed: {result.get('fail_closed') is True}")

sp_count = int(sp.get("symbol_count") or 0)
ndx_count = int(ndx.get("symbol_count") or 0)
passed = bool(
    tls.get("configured") is True
    and tls.get("certificate_verification") is True
    and tls.get("hostname_verification") is True
    and sp.get("verified_complete") is True
    and ndx.get("verified_complete") is True
    and sp.get("source_mode") == "OFFICIAL_WEB_SOURCE"
    and ndx.get("source_mode") == "OFFICIAL_WEB_SOURCE"
    and 490 <= sp_count <= 520
    and 95 <= ndx_count <= 110
    and result.get("verified_complete") is True
    and result.get("strict_membership") is True
    and 500 <= merged_count <= 620
)

if passed:
    print("RESULT: PASS — official S&P 500 + Nasdaq-100 universe verified with certificate validation enabled")
    raise SystemExit(0)

print("RESULT: FAIL — official production universe did not satisfy governed source/count validation")
raise SystemExit(1)
'''

    result = run(str(python), "-c", code, cwd=WORKTREE, check=False, env=env)

    branch_after = capture("git", "branch", "--show-current", cwd=LIVE)
    status_after = capture("git", "status", "--porcelain", cwd=LIVE)
    branch_unchanged = branch_after == branch_before
    status_unchanged = status_after == status_before

    print("\n=== OFFICIAL UNIVERSE ACCEPTANCE SAFETY SUMMARY ===")
    print(f"Live branch unchanged: {branch_unchanged} ({branch_after})")
    print(f"Live tracked status unchanged: {status_unchanged}")
    print(f"Runner exit code: {result.returncode}")

    if result.returncode == 0 and branch_unchanged and status_unchanged:
        print("FINAL RESULT: PASS")
        return 0

    print("FINAL RESULT: FAIL — inspect official-source output above; live lanes were not intentionally stopped")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
