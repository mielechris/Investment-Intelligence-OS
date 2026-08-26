#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

COMMIT_MESSAGE = "Wire Jesse live sources and scheduler"


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

    if not app_path.exists() or not panel_path.exists():
        raise SystemExit("Run this script from the Batch8 repository after git pull.")

    print("=== GROUP BATCH 8B - APPLY + VALIDATE ===")
    run(["git", "diff", "--check"], repo)
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    if status.strip():
        print("STOP: working tree is not clean")
        print(status)
        return 2

    app = app_path.read_text(encoding="utf-8")

    imports = (
        "from jesse_source_acquisition import router as jesse_source_acquisition_router\n"
        "from jesse_scheduler import router as jesse_scheduler_router, start_jesse_scheduler, stop_jesse_scheduler\n"
    )
    app = patch_after(
        app,
        "from thesis_integrity_v2 import thesis_integrity_evidence, router as thesis_integrity_v2_router\n",
        imports,
        "8B imports",
    )

    routers = (
        "app.include_router(jesse_source_acquisition_router)\n"
        "app.include_router(jesse_scheduler_router)\n"
    )
    app = patch_after(
        app,
        "app.include_router(thesis_integrity_v2_router)\n",
        routers,
        "8B routers",
    )

    flags = (
        '        "jesse_live_source_acquisition": True,\n'
        '        "jesse_internal_scheduler": True,\n'
        '        "dislocation_11am_pacific_scheduler": True,\n'
        '        "dislocation_next_day_calibration": True,\n'
        '        "authorized_research_inbox": True,\n'
        '        "governed_fed_probability_feed_adapter": True,\n'
        '        "governed_dislocation_universe_registry": True,\n'
    )
    app = patch_after(
        app,
        '        "generic_thesis_integrity_v2": True,\n',
        flags,
        "8B status flags",
    )

    if "    start_jesse_scheduler()\n" not in app:
        anchor = "    start_opportunity_scheduler()\n"
        if anchor not in app:
            raise RuntimeError("startup anchor not found")
        app = app.replace(anchor, anchor + "    start_jesse_scheduler()\n", 1)

    if "    stop_jesse_scheduler()\n" not in app:
        anchor = "    stop_opportunity_scheduler()\n"
        if anchor not in app:
            raise RuntimeError("shutdown anchor not found")
        app = app.replace(anchor, anchor + "    stop_jesse_scheduler()\n", 1)

    app = app.replace('app.version = "0.14.0"', 'app.version = "0.15.0"')
    app = app.replace('"version": "0.14.0"', '"version": "0.15.0"')
    app = app.replace("Investment-Intelligence-OS/0.14.0", "Investment-Intelligence-OS/0.15.0")
    app_path.write_text(app, encoding="utf-8")

    panel = panel_path.read_text(encoding="utf-8")
    if "/intelligence/jesse-scheduler/status" not in panel:
        panel = panel.replace(
            "const [s,f,t,d]=await Promise.all([",
            "const [s,f,t,d,j,a]=await Promise.all([",
            1,
        )
        panel = panel.replace(
            "      fetch(`${API}/intelligence/dislocation/status`).then(r=>r.json())\n",
            "      fetch(`${API}/intelligence/dislocation/status`).then(r=>r.json()),\n"
            "      fetch(`${API}/intelligence/jesse-scheduler/status`).then(r=>r.json()),\n"
            "      fetch(`${API}/intelligence/source-acquisition/status`).then(r=>r.json())\n",
            1,
        )
        panel = panel.replace("if(active)setData({s,f,t,d});", "if(active)setData({s,f,t,d,j,a});", 1)
        marker = '      <div style={card}><b>Daily dislocation scanner</b>'
        addition = (
            '      <div style={card}><b>Production scheduler</b>'
            '<div>{data.j?.scheduler_running ? "RUNNING" : "STOPPED"}</div>'
            '<div>11AM PT last run: {data.j?.state?.last_dislocation_date || "—"}</div>'
            '<div>Calibration observations: {data.j?.calibration?.observation_count ?? 0}</div></div>\n'
            '      <div style={card}><b>Live source acquisition</b>'
            '<div>Research discoveries: {data.a?.institutional_discovery?.discovery_count ?? 0}</div>'
            '<div>Strict universe: {data.a?.governed_dislocation_universe?.symbol_count ?? 0} symbols</div>'
            '<div>Fed feed configured: {data.a?.fed_probability_url_configured ? "YES" : "FILE / NOT CONFIGURED"}</div></div>\n'
        )
        if marker not in panel:
            raise RuntimeError("Jesse panel marker not found")
        panel = panel.replace(marker, addition + marker, 1)
        panel_path.write_text(panel, encoding="utf-8")

    run(["git", "diff", "--check"], repo)

    sibling_venv = repo.parent / "Investment-Intelligence-OS" / "BACK END" / "backend" / ".venv" / "bin" / "python"
    py = str(sibling_venv if sibling_venv.exists() else Path(sys.executable))

    run(
        [py, "-m", "py_compile", "jesse_source_acquisition.py", "jesse_scheduler.py", "test_group_batch8b_live_sources.py", "app.py"],
        backend,
    )
    run(
        [
            py, "-m", "unittest", "-v",
            "test_group_batch8b_live_sources.py",
            "test_group_batch8a_jesse_intelligence.py",
            "test_group_batch7_factory_genericization.py",
            "test_group_batch6_generic_coverage.py",
        ],
        backend,
    )
    run(["npm", "run", "build"], frontend)

    run(["git", "diff", "--stat"], repo)
    run(["git", "status", "-sb"], repo)

    run(["git", "add", "BACK END/backend/app.py", "FRONT END/src/JesseIntelligencePanel.tsx"], repo)
    run(["git", "diff", "--cached", "--check"], repo)
    commit = run(["git", "commit", "-m", COMMIT_MESSAGE], repo, check=False)
    if commit.returncode != 0:
        return commit.returncode

    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
    run(["git", "push", "origin", branch], repo)

    print()
    print("============================================================")
    print("GROUP BATCH 8B COMPLETE")
    print("Public institutional research discovery: INSTALLED")
    print("Authorized research inbox: INSTALLED")
    print("Governed Fed probability feed adapter: INSTALLED")
    print("Strict dislocation universe registry: INSTALLED")
    print("11AM Pacific dislocation scheduler: INSTALLED")
    print("Hourly tariff/Fed refresh: INSTALLED")
    print("Next-day +5% outcome calibration: INSTALLED")
    print("IIOS version: 0.15.0")
    print("Live execution authority: FALSE")
    print("============================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
