#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

COMMIT_MESSAGE = "Integrate Batch 8E multi-model intelligence council"


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    dirs = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        str(Path.home() / ".volta" / "bin"),
        str(Path.home() / ".local" / "bin"),
    ]
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.exists():
        dirs.extend(str(p / "bin") for p in sorted(nvm.iterdir(), reverse=True) if (p / "bin").exists())
    current = env.get("PATH", "")
    env["PATH"] = ":".join([*dirs, current])
    return env


ENV = runtime_env()


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=ENV)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, env=ENV, text=True).strip()


def npm_command() -> str:
    found = shutil.which("npm", path=ENV.get("PATH"))
    if found:
        return found
    raise RuntimeError("npm not found after expanding unattended PATH")


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
        backend / "grok_provider.py",
        backend / "multi_model_intelligence_council.py",
        backend / "test_group_batch8e_multi_model_council.py",
        backend / "test_group_batch8d_kimi_research.py",
        backend / "test_governed_chain_end_to_end.py",
        repo / "scripts" / "smoke_batch8e_live.py",
        app_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("STOP: Batch 8E files missing. Supervisor should pull again.")
        for path in missing:
            print(" ", path)
        return 2

    print("=" * 72)
    print("GROUP BATCH 8E - MULTI-MODEL INTELLIGENCE COUNCIL")
    print("=" * 72)

    branch = output(["git", "branch", "--show-current"], repo)
    if branch != "feature/batch8-paper-portfolio":
        print("STOP: wrong branch:", branch)
        return 2

    run(["git", "diff", "--check"], repo)
    if output(["git", "status", "--porcelain"], repo):
        print("STOP: working tree is not clean")
        print(output(["git", "status", "--short"], repo))
        return 2

    original_app = app_path.read_text(encoding="utf-8")
    app = original_app
    already_integrated = (
        "from multi_model_intelligence_council import council_evidence, router as multi_model_council_router" in app
        and 'app.version = "0.18.0"' in app
    )
    changed = False
    committed = already_integrated

    try:
        if not already_integrated:
            import_line = (
                "from multi_model_intelligence_council import council_evidence, "
                "router as multi_model_council_router\n"
            )
            app = patch_after(
                app,
                "from kimi_research_intelligence import kimi_research_evidence, router as kimi_research_router\n",
                import_line,
                "Batch 8E import",
            )

            app = patch_after(
                app,
                "        items.extend(kimi_research_evidence(case_id))\n",
                "        items.extend(council_evidence(case_id))\n",
                "Batch 8E context injection",
            )

            app = patch_after(
                app,
                "app.include_router(kimi_research_router)\n",
                "app.include_router(multi_model_council_router)\n",
                "Batch 8E router",
            )

            flags = (
                '        "multi_model_intelligence_council": True,\n'
                '        "grok_x_search_intelligence": True,\n'
                '        "grok_web_search_intelligence": True,\n'
                '        "model_divergence_skeptic_escalation": True,\n'
                '        "universal_model_weighting": False,\n'
                '        "multi_model_committee_override": False,\n'
                '        "multi_model_risk_override": False,\n'
                '        "grok_auto_trade_authority": False,\n'
            )
            app = patch_after(
                app,
                '        "kimi_auto_trade_authority": False,\n',
                flags,
                "Batch 8E status flags",
            )

            if 'app.version = "0.17.0"' not in app and 'app.version = "0.18.0"' not in app:
                raise RuntimeError("Unexpected IIOS app version before Batch 8E")
            app = app.replace('app.version = "0.17.0"', 'app.version = "0.18.0"')
            app = app.replace('"version": "0.17.0"', '"version": "0.18.0"')
            app = app.replace("Investment-Intelligence-OS/0.17.0", "Investment-Intelligence-OS/0.18.0")
            app_path.write_text(app, encoding="utf-8")
            changed = True
        else:
            print("Batch 8E app integration already present; validating and re-running smoke.")

        run(["git", "diff", "--check"], repo)

        sibling_venv = (
            repo.parent / "Investment-Intelligence-OS" / "BACK END" / "backend" / ".venv" / "bin" / "python"
        )
        py = str(sibling_venv if sibling_venv.exists() else Path(sys.executable))

        print("\n=== PYTHON COMPILE ===")
        run(
            [
                py, "-m", "py_compile",
                "grok_provider.py",
                "multi_model_intelligence_council.py",
                "test_group_batch8e_multi_model_council.py",
                "kimi_provider.py",
                "kimi_swarm_bridge.py",
                "kimi_research_intelligence.py",
                "app.py",
            ],
            backend,
        )

        print("\n=== BATCH 8E + REGRESSION TESTS ===")
        run(
            [
                py, "-m", "unittest", "-v",
                "test_group_batch8e_multi_model_council.py",
                "test_group_batch8d_kimi_research.py",
                "test_group_batch8c_production_inputs.py",
                "test_group_batch8b_live_sources.py",
                "test_group_batch8a_jesse_intelligence.py",
                "test_group_batch7_factory_genericization.py",
                "test_group_batch6_generic_coverage.py",
                "test_governed_chain_end_to_end.py",
            ],
            backend,
        )

        print("\n=== FRONTEND REGRESSION BUILD ===")
        run([npm_command(), "run", "build"], frontend)

        print("\n=== INTEGRATION DIFF ===")
        run(["git", "diff", "--stat"], repo)
        run(["git", "status", "-sb"], repo)

        run(["git", "add", "BACK END/backend/app.py"], repo)
        run(["git", "diff", "--cached", "--check"], repo)
        staged = output(["git", "diff", "--cached", "--name-only"], repo)
        if staged:
            run(["git", "diff", "--cached", "--stat"], repo)
            run(["git", "commit", "-m", COMMIT_MESSAGE], repo)
            committed = True
        else:
            print("No new integration diff to commit.")

        # Always push. This makes a retry recover cleanly if a prior push failed.
        run(["git", "push", "origin", branch], repo)

        print("\n=== LIVE BATCH 8E SMOKE ===")
        smoke = run([py, str(repo / "scripts" / "smoke_batch8e_live.py")], repo, check=False)
        if smoke.returncode != 0:
            print("Batch 8E integration is present, but live smoke needs attention.")
            return smoke.returncode

        print("\n" + "=" * 72)
        print("GROUP BATCH 8E COMPLETE")
        print("IIOS version: 0.18.0")
        print("IIOS/OpenAI governed core view: INSTALLED")
        print("Kimi deep-research view: INSTALLED")
        print("Grok X + web narrative provider: INSTALLED / CONFIG-GATED")
        print("Model disagreement engine: INSTALLED")
        print("Skeptic escalation on meaningful divergence: INSTALLED")
        print("Universal model weighting: FALSE")
        print("Committee / Risk override: FALSE")
        print("Capital / trade authority: FALSE")
        print("Live execution authority: FALSE")
        print("=" * 72)
        return 0

    except Exception as exc:
        print(f"Batch 8E apply error: {type(exc).__name__}: {exc}")
        if changed and not committed:
            try:
                subprocess.run(
                    ["git", "restore", "--staged", "--", "BACK END/backend/app.py"],
                    cwd=repo,
                    env=ENV,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                app_path.write_text(original_app, encoding="utf-8")
                print("Rolled back partial Batch 8E app.py integration; working tree preserved clean.")
            except Exception as rollback_exc:
                print("Rollback warning:", rollback_exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
