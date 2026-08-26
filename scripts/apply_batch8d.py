#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


COMMIT_MESSAGE = "Integrate Batch 8D Kimi research intelligence"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


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

    required = [
        backend / "kimi_provider.py",
        backend / "kimi_swarm_bridge.py",
        backend / "kimi_research_intelligence.py",
        backend / "test_group_batch8d_kimi_research.py",
        repo / "scripts" / "smoke_batch8d_live.py",
        app_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("STOP: Batch 8D files missing. Supervisor should pull again.")
        for path in missing:
            print(" ", path)
        return 2

    print("=" * 72)
    print("GROUP BATCH 8D - KIMI RESEARCH & SWARM INTELLIGENCE")
    print("=" * 72)

    branch = output(["git", "branch", "--show-current"], repo)
    if branch != "feature/batch8-paper-portfolio":
        print("STOP: wrong branch:", branch)
        return 2

    run(["git", "diff", "--check"], repo)
    status = output(["git", "status", "--porcelain"], repo)
    if status:
        print("STOP: working tree is not clean")
        print(status)
        return 2

    app = app_path.read_text(encoding="utf-8")
    already_integrated = (
        "from kimi_research_intelligence import kimi_research_evidence, router as kimi_research_router" in app
        and 'app.version = "0.17.0"' in app
    )

    if not already_integrated:
        import_line = (
            "from kimi_research_intelligence import kimi_research_evidence, "
            "router as kimi_research_router\n"
        )
        app = patch_after(
            app,
            "from batch8c_production_inputs import install_batch8c, router as batch8c_production_inputs_router\n",
            import_line,
            "Batch 8D import",
        )

        evidence_line = "        items.extend(kimi_research_evidence(case_id))\n"
        app = patch_after(
            app,
            "        items.extend(institutional_research_evidence(case_id))\n",
            evidence_line,
            "Batch 8D governed context injection",
        )

        router_line = "app.include_router(kimi_research_router)\n"
        app = patch_after(
            app,
            "app.include_router(batch8c_production_inputs_router)\n",
            router_line,
            "Batch 8D router",
        )

        flags = (
            '        "kimi_research_intelligence": True,\n'
            '        "kimi_k3_long_context_research": True,\n'
            '        "kimi_iios_parallel_research": True,\n'
            '        "kimi_native_swarm_bridge": True,\n'
            '        "kimi_formula_web_search": True,\n'
            '        "kimi_consumer_deep_research_api_claimed": False,\n'
            '        "kimi_full_report_persistence": False,\n'
            '        "kimi_context_only_default": True,\n'
            '        "kimi_auto_trade_authority": False,\n'
        )
        app = patch_after(
            app,
            '        "production_inputs_fail_closed": True,\n',
            flags,
            "Batch 8D status flags",
        )

        if 'app.version = "0.16.0"' not in app and 'app.version = "0.17.0"' not in app:
            raise RuntimeError("Unexpected IIOS app version before Batch 8D")
        app = app.replace('app.version = "0.16.0"', 'app.version = "0.17.0"')
        app = app.replace('"version": "0.16.0"', '"version": "0.17.0"')
        app = app.replace("Investment-Intelligence-OS/0.16.0", "Investment-Intelligence-OS/0.17.0")
        app_path.write_text(app, encoding="utf-8")
    else:
        print("Batch 8D app integration already present; validating and re-running smoke.")

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
            "kimi_provider.py",
            "kimi_swarm_bridge.py",
            "kimi_research_intelligence.py",
            "test_group_batch8d_kimi_research.py",
            "app.py",
        ],
        backend,
    )

    print("\n=== BATCH 8D + REGRESSION TESTS ===")
    run(
        [
            py,
            "-m",
            "unittest",
            "-v",
            "test_group_batch8d_kimi_research.py",
            "test_group_batch8c_production_inputs.py",
            "test_group_batch8b_live_sources.py",
            "test_group_batch8a_jesse_intelligence.py",
            "test_group_batch7_factory_genericization.py",
            "test_group_batch6_generic_coverage.py",
        ],
        backend,
    )

    print("\n=== FRONTEND REGRESSION BUILD ===")
    run(["npm", "run", "build"], frontend)

    print("\n=== INTEGRATION DIFF ===")
    run(["git", "diff", "--stat"], repo)
    run(["git", "status", "-sb"], repo)

    run(["git", "add", "BACK END/backend/app.py"], repo)
    run(["git", "diff", "--cached", "--check"], repo)
    staged = output(["git", "diff", "--cached", "--name-only"], repo)
    if staged:
        run(["git", "diff", "--cached", "--stat"], repo)
        run(["git", "commit", "-m", COMMIT_MESSAGE], repo)
        run(["git", "push", "origin", branch], repo)
    else:
        print("No new integration diff to commit; continuing to live smoke.")

    print("\n=== LIVE BATCH 8D SMOKE ===")
    smoke = run([py, str(repo / "scripts" / "smoke_batch8d_live.py")], repo, check=False)
    if smoke.returncode != 0:
        print("Batch 8D integration is present, but live smoke needs attention.")
        return smoke.returncode

    print("\n" + "=" * 72)
    print("GROUP BATCH 8D COMPLETE")
    print("IIOS version: 0.17.0")
    print("Kimi K3 provider adapter: INSTALLED")
    print("Kimi long-context normalized research: INSTALLED")
    print("IIOS-managed parallel Kimi research: INSTALLED")
    print("Kimi Formula web-search bridge: INSTALLED")
    print("Optional native Kimi Code Swarm bridge: INSTALLED / CONFIG-GATED")
    print("Full proprietary report persistence: FALSE")
    print("Qualification / gap-resolution authority: FALSE")
    print("Capital / trade authority: FALSE")
    print("Live execution authority: FALSE")
    print("Kimi credential is only required for live provider validation.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
