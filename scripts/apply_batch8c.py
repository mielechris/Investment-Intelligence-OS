#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


COMMIT_MESSAGE = "Finish Batch 8C production inputs"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def patch_after(text: str, anchor: str, addition: str, label: str) -> str:
    if addition in text:
        return text
    if anchor not in text:
        raise RuntimeError(f"Patch anchor not found: {label}")
    return text.replace(anchor, anchor + addition, 1)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    backend = repo / "BACK END" / "backend"
    frontend = repo / "FRONT END"
    app_path = backend / "app.py"
    panel_path = frontend / "src" / "JesseIntelligencePanel.tsx"

    required = [
        backend / "production_index_universe.py",
        backend / "cme_fedwatch_adapter.py",
        backend / "batch8c_production_inputs.py",
        backend / "test_group_batch8c_production_inputs.py",
        repo / "scripts" / "smoke_batch8c_live.py",
        app_path,
        panel_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("STOP: Batch 8C files missing. Run git pull first.")
        for path in missing:
            print(" ", path)
        return 2

    print("=" * 72)
    print("GROUP BATCH 8C - APPLY + VALIDATE + PUSH + LIVE SMOKE")
    print("=" * 72)

    run(["git", "diff", "--check"], repo)
    status = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=repo,
        text=True,
    )
    if status.strip():
        print("STOP: working tree is not clean")
        print(status)
        return 2

    app = app_path.read_text(encoding="utf-8")

    batch8c_import = (
        "from batch8c_production_inputs import install_batch8c, "
        "router as batch8c_production_inputs_router\n"
    )
    app = patch_after(
        app,
        "from jesse_scheduler import router as jesse_scheduler_router, start_jesse_scheduler, stop_jesse_scheduler\n",
        batch8c_import,
        "Batch 8C integration import",
    )

    install_line = "install_batch8c()\n"
    app = patch_after(
        app,
        "install_required_evidence_risk_guard(primary_evidence)\n",
        install_line,
        "Batch 8C install call",
    )

    router_line = "app.include_router(batch8c_production_inputs_router)\n"
    app = patch_after(
        app,
        "app.include_router(jesse_scheduler_router)\n",
        router_line,
        "Batch 8C router",
    )

    flags = (
        '        "automatic_official_index_universe_refresh": True,\n'
        '        "strict_scheduled_dislocation_universe": True,\n'
        '        "cme_fedwatch_production_adapter": True,\n'
        '        "cme_fedwatch_eod_realtime_modes": True,\n'
        '        "production_input_source_health": True,\n'
        '        "production_inputs_fail_closed": True,\n'
    )
    app = patch_after(
        app,
        '        "governed_dislocation_universe_registry": True,\n',
        flags,
        "Batch 8C status flags",
    )

    app = app.replace('app.version = "0.15.0"', 'app.version = "0.16.0"')
    app = app.replace('"version": "0.15.0"', '"version": "0.16.0"')
    app = app.replace("Investment-Intelligence-OS/0.15.0", "Investment-Intelligence-OS/0.16.0")
    app_path.write_text(app, encoding="utf-8")

    panel = panel_path.read_text(encoding="utf-8")
    if "Production universe:" not in panel:
        old = (
            '      <div style={card}><b>Live source acquisition</b>'
            '<div>Research discoveries: {data.a?.institutional_discovery?.discovery_count ?? 0}</div>'
            '<div>Strict universe: {data.a?.governed_dislocation_universe?.symbol_count ?? 0} symbols</div>'
            '<div>Fed feed configured: {data.a?.fed_probability_url_configured ? "YES" : "FILE / NOT CONFIGURED"}</div></div>'
        )
        new = (
            '      <div style={card}><b>Production input health</b>'
            '<div>Research discoveries: {data.a?.institutional_discovery?.discovery_count ?? 0}</div>'
            '<div>Production universe: {data.a?.strict_universe_verified ? "VERIFIED" : "NOT READY"} · {data.a?.production_index_universe?.symbol_count ?? 0} symbols</div>'
            '<div>Universe source: {(data.a?.production_index_universe?.source_lineage || []).map((x:any)=>`${x.index}:${x.verified_complete ? "OK" : "FAIL"}`).join(" · ") || "—"}</div>'
            '<div>CME FedWatch: {data.a?.cme_fedwatch?.configured ? `${data.a?.cme_fedwatch?.mode || "EOD"} CONFIGURED` : "NOT CONFIGURED"}</div>'
            '<div>Fed snapshot verified: {data.a?.cme_fedwatch?.latest_snapshot_source_verified ? "YES" : "NO"}</div>'
            '<div>Fail closed: {data.a?.production_inputs_fail_closed ? "YES" : "—"}</div></div>'
        )
        if old not in panel:
            raise RuntimeError("Jesse Intelligence Floor source card anchor not found")
        panel = panel.replace(old, new, 1)
        panel_path.write_text(panel, encoding="utf-8")

    run(["git", "diff", "--check"], repo)

    sibling_venv = (
        repo.parent
        / "Investment-Intelligence-OS"
        / "BACK END"
        / "backend"
        / ".venv"
        / "bin"
        / "python"
    )
    py = str(sibling_venv if sibling_venv.exists() else Path(sys.executable))

    print("\n=== PYTHON COMPILE ===")
    run(
        [
            py,
            "-m",
            "py_compile",
            "production_index_universe.py",
            "cme_fedwatch_adapter.py",
            "batch8c_production_inputs.py",
            "test_group_batch8c_production_inputs.py",
            "jesse_source_acquisition.py",
            "jesse_scheduler.py",
            "dislocation_intelligence.py",
            "macro_policy_intelligence.py",
            "app.py",
        ],
        backend,
    )

    print("\n=== REGRESSION TESTS ===")
    run(
        [
            py,
            "-m",
            "unittest",
            "-v",
            "test_group_batch8c_production_inputs.py",
            "test_group_batch8b_live_sources.py",
            "test_group_batch8a_jesse_intelligence.py",
            "test_group_batch7_factory_genericization.py",
            "test_group_batch6_generic_coverage.py",
        ],
        backend,
    )

    print("\n=== FRONTEND BUILD ===")
    run(["npm", "run", "build"], frontend)

    print("\n=== DIFF REVIEW ===")
    run(["git", "diff", "--stat"], repo)
    run(["git", "status", "-sb"], repo)

    # The production modules/tests/smoke/apply files arrived in the preceding
    # GitHub commits. This apply command modifies only the two integration files.
    run(
        [
            "git",
            "add",
            "BACK END/backend/app.py",
            "FRONT END/src/JesseIntelligencePanel.tsx",
        ],
        repo,
    )
    run(["git", "diff", "--cached", "--check"], repo)
    run(["git", "diff", "--cached", "--stat"], repo)

    commit = run(["git", "commit", "-m", COMMIT_MESSAGE], repo, check=False)
    if commit.returncode != 0:
        return commit.returncode

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=repo,
        text=True,
    ).strip()
    run(["git", "push", "origin", branch], repo)

    print("\n=== LIVE BATCH 8C SMOKE ===")
    smoke = run([py, str(repo / "scripts" / "smoke_batch8c_live.py")], repo, check=False)
    if smoke.returncode != 0:
        print("Batch 8C code was committed/pushed, but live smoke needs attention.")
        return smoke.returncode

    print("\n" + "=" * 72)
    print("GROUP BATCH 8C SOFTWARE COMPLETE")
    print("IIOS version: 0.16.0")
    print("Official index universe adapter: INSTALLED")
    print("Strict scheduled 11AM universe: INSTALLED / FAIL-CLOSED")
    print("CME FedWatch EOD + REALTIME adapter: INSTALLED")
    print("Source health on Jesse Intelligence Floor: INSTALLED")
    print("Next-day dislocation calibration: PRESERVED")
    print("Live execution authority: FALSE")
    print("External feed readiness is reported by the live smoke; it is never fabricated.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
