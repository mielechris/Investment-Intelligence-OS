#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

BRANCH = "feature/batch8-paper-portfolio"
COMMIT_MESSAGE = "Integrate Batch 8G Factory Intelligence UI"


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    extra = [
        "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
        "/usr/sbin", "/sbin", str(Path.home() / ".volta" / "bin"),
        str(Path.home() / ".local" / "bin"),
    ]
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.exists():
        extra.extend(
            str(path / "bin")
            for path in sorted(nvm.iterdir(), reverse=True)
            if (path / "bin").exists()
        )
    env["PATH"] = ":".join([*extra, env.get("PATH", "")])
    return env


ENV = runtime_env()


def run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=cwd, env=ENV)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")
    return result


def output(command: list[str], cwd: Path) -> str:
    return subprocess.check_output(command, cwd=cwd, env=ENV, text=True).strip()


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
    ui_path = frontend / "src" / "FactoryIntelligenceUI.tsx"
    required = [
        backend / "factory_intelligence_ui.py",
        backend / "test_group_batch8g_factory_intelligence_ui.py",
        ui_path,
        frontend / "src" / "FactoryIntelligenceUI.css",
        frontend / "src" / "main.tsx",
        repo / "scripts" / "smoke_batch8g_live.py",
        app_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("STOP: Batch 8G files missing")
        print("\n".join(f"  {path}" for path in missing))
        return 2
    if output(["git", "branch", "--show-current"], repo) != BRANCH:
        print("STOP: wrong branch")
        return 2
    run(["git", "diff", "--check"], repo)
    if output(["git", "status", "--porcelain"], repo):
        print("STOP: working tree is not clean")
        print(output(["git", "status", "--short"], repo))
        return 2

    original = app_path.read_text(encoding="utf-8")
    original_ui = ui_path.read_text(encoding="utf-8")
    text = original
    ui_text = original_ui
    integrated = (
        "from factory_intelligence_ui import router as factory_intelligence_ui_router" in text
        and 'app.version = "0.20.0"' in text
    )
    changed = False
    frontend_changed = False
    committed = integrated
    print("=" * 72)
    print("GROUP BATCH 8G - FACTORY INTELLIGENCE UI")
    print("=" * 72)

    try:
        broken_capital_panel = "<PaperCapitalControlPanel />"
        fixed_capital_panel = (
            "<PaperCapitalControlPanel caseId={activeCaseId} />"
        )
        if broken_capital_panel in ui_text:
            ui_text = ui_text.replace(
                broken_capital_panel,
                fixed_capital_panel,
                1,
            )
            ui_path.write_text(ui_text, encoding="utf-8")
            frontend_changed = True
            changed = True
            print("Repaired Factory Intelligence capital-panel case binding.")
        elif fixed_capital_panel not in ui_text:
            raise RuntimeError(
                "Unexpected Factory Intelligence capital-panel binding"
            )

        if not integrated:
            text = patch_after(
                text,
                "from model_scale_validation import router as model_scale_validation_router\n",
                "from factory_intelligence_ui import router as factory_intelligence_ui_router\n",
                "Batch 8G import",
            )
            text = patch_after(
                text,
                "app.include_router(model_scale_validation_router)\n",
                "app.include_router(factory_intelligence_ui_router)\n",
                "Batch 8G router",
            )
            flags = (
                '        "factory_intelligence_ui": True,\n'
                '        "factory_intelligence_live_overview": True,\n'
                '        "factory_model_council_visualization": True,\n'
                '        "factory_task_calibration_visualization": True,\n'
                '        "factory_ui_unknown_state_semantics": True,\n'
                '        "factory_ui_read_only_aggregation": True,\n'
                '        "factory_ui_decision_authority": False,\n'
                '        "factory_ui_trade_authority": False,\n'
            )
            text = patch_after(
                text,
                '        "calibration_auto_trade_authority": False,\n',
                flags,
                "Batch 8G system flags",
            )
            if 'app.version = "0.19.0"' not in text:
                raise RuntimeError("Unexpected IIOS version before Batch 8G")
            text = text.replace("0.19.0", "0.20.0")
            app_path.write_text(text, encoding="utf-8")
            changed = True
        else:
            print("Batch 8G app integration already present; validating again.")

        sibling = repo.parent / "Investment-Intelligence-OS" / "BACK END" / "backend" / ".venv" / "bin" / "python"
        python = str(sibling if sibling.exists() else Path(sys.executable))
        npm = shutil.which("npm", path=ENV.get("PATH"))
        if not npm:
            raise RuntimeError("npm not found")

        run(["git", "diff", "--check"], repo)
        run([
            python, "-m", "py_compile", "app.py", "factory_intelligence_ui.py",
            "test_group_batch8g_factory_intelligence_ui.py", "model_scale_validation.py",
            "multi_model_intelligence_council.py",
        ], backend)
        run([
            python, "-c",
            "import app; "
            "version=getattr(app.app,'version',None); "
            "paths=sorted(str(getattr(r,'path','')) for r in app.app.routes); "
            "print('IIOS runtime version:', version); "
            "print('IIOS route count:', len(paths)); "
            "assert version == '0.20.0', version",
        ], backend)
        run([
            python, "-m", "unittest", "-v",
            "test_group_batch8g_factory_intelligence_ui.py",
            "test_group_batch8f_scale_validation.py",
            "test_group_batch8e_multi_model_council.py",
            "test_group_batch8d_kimi_research.py",
            "test_group_batch8c_production_inputs.py",
            "test_group_batch8b_live_sources.py",
            "test_group_batch8a_jesse_intelligence.py",
            "test_group_batch7_factory_genericization.py",
            "test_group_batch6_generic_coverage.py",
            "test_governed_chain_end_to_end.py",
        ], backend)
        run([npm, "run", "build"], frontend)

        run([
            "git", "add",
            "BACK END/backend/app.py",
            "FRONT END/src/FactoryIntelligenceUI.tsx",
        ], repo)
        run(["git", "diff", "--cached", "--check"], repo)
        if output(["git", "diff", "--cached", "--name-only"], repo):
            run(["git", "commit", "-m", COMMIT_MESSAGE], repo)
            committed = True
        else:
            print("No new integration diff to commit.")
        run(["git", "push", "origin", BRANCH], repo)

        smoke = run([python, str(repo / "scripts" / "smoke_batch8g_live.py")], repo, check=False)
        if smoke.returncode:
            print("Batch 8G is integrated, but live smoke needs attention.")
            return smoke.returncode

        print("=" * 72)
        print("GROUP BATCH 8G COMPLETE")
        print("IIOS version: 0.20.0")
        print("Factory Intelligence UI: INSTALLED")
        print("Unknown / offline truth states: ENFORCED")
        print("Read-only aggregation: TRUE")
        print("Committee / Risk override: FALSE")
        print("Capital / trade authority: FALSE")
        print("Live execution authority: FALSE")
        print("=" * 72)
        return 0
    except Exception as exc:
        print(f"Batch 8G apply error: {type(exc).__name__}: {exc}")
        if changed and not committed:
            try:
                subprocess.run(
                    [
                        "git", "restore", "--staged", "--",
                        "BACK END/backend/app.py",
                        "FRONT END/src/FactoryIntelligenceUI.tsx",
                    ],
                    cwd=repo, env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                app_path.write_text(original, encoding="utf-8")
                if frontend_changed:
                    ui_path.write_text(original_ui, encoding="utf-8")
                print("Rolled back partial Batch 8G integration.")
            except Exception as rollback_exc:
                print("Rollback warning:", rollback_exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
