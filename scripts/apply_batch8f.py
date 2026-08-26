#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


COMMIT_MESSAGE = (
    "Integrate Batch 8F scale validation "
    "and task calibration"
)


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
    nvm = (
        Path.home()
        / ".nvm"
        / "versions"
        / "node"
    )
    if nvm.exists():
        dirs.extend(
            str(path / "bin")
            for path in sorted(
                nvm.iterdir(),
                reverse=True,
            )
            if (path / "bin").exists()
        )
    current = env.get("PATH", "")
    env["PATH"] = ":".join(
        [*dirs, current]
    )
    return env


ENV = runtime_env()


def run(
    cmd: list[str],
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=ENV,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed "
            f"({result.returncode}): "
            + " ".join(cmd)
        )
    return result


def output(
    cmd: list[str],
    cwd: Path,
) -> str:
    return subprocess.check_output(
        cmd,
        cwd=cwd,
        env=ENV,
        text=True,
    ).strip()


def npm_command() -> str:
    found = shutil.which(
        "npm",
        path=ENV.get("PATH"),
    )
    if found:
        return found
    raise RuntimeError(
        "npm not found after expanding "
        "unattended PATH"
    )


def patch_after(
    text: str,
    anchor: str,
    addition: str,
    label: str,
) -> str:
    if addition in text:
        return text
    if anchor not in text:
        raise RuntimeError(
            f"Patch anchor not found: {label}"
        )
    return text.replace(
        anchor,
        anchor + addition,
        1,
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    backend = repo / "BACK END" / "backend"
    frontend = repo / "FRONT END"
    app_path = backend / "app.py"

    required = [
        backend
        / "model_scale_validation.py",
        backend
        / "test_group_batch8f_scale_validation.py",
        backend
        / "multi_model_intelligence_council.py",
        backend
        / "test_group_batch8e_multi_model_council.py",
        backend
        / "test_group_batch8d_kimi_research.py",
        backend
        / "test_governed_chain_end_to_end.py",
        repo
        / "scripts"
        / "smoke_batch8f_live.py",
        app_path,
    ]
    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]
    if missing:
        print(
            "STOP: Batch 8F files missing. "
            "Supervisor should pull again."
        )
        for path in missing:
            print(" ", path)
        return 2

    print("=" * 72)
    print(
        "GROUP BATCH 8F - SCALE VALIDATION "
        "AND TASK CALIBRATION"
    )
    print("=" * 72)

    branch = output(
        ["git", "branch", "--show-current"],
        repo,
    )
    if branch != (
        "feature/batch8-paper-portfolio"
    ):
        print("STOP: wrong branch:", branch)
        return 2

    run(["git", "diff", "--check"], repo)
    if output(
        ["git", "status", "--porcelain"],
        repo,
    ):
        print(
            "STOP: working tree is not clean"
        )
        print(
            output(
                ["git", "status", "--short"],
                repo,
            )
        )
        return 2

    original_app = app_path.read_text(
        encoding="utf-8"
    )
    app = original_app
    already_integrated = (
        (
            "from model_scale_validation "
            "import router as "
            "model_scale_validation_router"
        )
        in app
        and 'app.version = "0.19.0"' in app
    )
    changed = False
    committed = already_integrated

    try:
        if not already_integrated:
            import_line = (
                "from model_scale_validation "
                "import router as "
                "model_scale_validation_router\n"
            )
            app = patch_after(
                app,
                (
                    "from "
                    "multi_model_intelligence_council "
                    "import council_evidence, "
                    "router as "
                    "multi_model_council_router\n"
                ),
                import_line,
                "Batch 8F import",
            )

            app = patch_after(
                app,
                (
                    "app.include_router("
                    "multi_model_council_router)\n"
                ),
                (
                    "app.include_router("
                    "model_scale_validation_router)\n"
                ),
                "Batch 8F router",
            )

            flags = (
                '        "multi_model_scale_validation": True,\n'
                '        "task_specific_model_calibration": True,\n'
                '        "model_calibration_minimum_samples_required": True,\n'
                '        "model_calibration_manual_promotion_only": True,\n'
                '        "model_calibration_automatically_applied_to_council": False,\n'
                '        "calibration_committee_override": False,\n'
                '        "calibration_risk_override": False,\n'
                '        "calibration_auto_trade_authority": False,\n'
            )
            app = patch_after(
                app,
                (
                    '        "grok_auto_trade_authority": '
                    'False,\n'
                ),
                flags,
                "Batch 8F status flags",
            )

            if (
                'app.version = "0.18.0"'
                not in app
                and
                'app.version = "0.19.0"'
                not in app
            ):
                raise RuntimeError(
                    "Unexpected IIOS app version "
                    "before Batch 8F"
                )
            app = app.replace(
                'app.version = "0.18.0"',
                'app.version = "0.19.0"',
            )
            app = app.replace(
                '"version": "0.18.0"',
                '"version": "0.19.0"',
            )
            app = app.replace(
                (
                    "Investment-Intelligence-OS/"
                    "0.18.0"
                ),
                (
                    "Investment-Intelligence-OS/"
                    "0.19.0"
                ),
            )
            app_path.write_text(
                app,
                encoding="utf-8",
            )
            changed = True
        else:
            print(
                "Batch 8F app integration already "
                "present; validating and "
                "re-running smoke."
            )

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
        py = str(
            sibling_venv
            if sibling_venv.exists()
            else Path(sys.executable)
        )

        print("\n=== PYTHON COMPILE ===")
        run(
            [
                py,
                "-m",
                "py_compile",
                "model_scale_validation.py",
                (
                    "test_group_batch8f_"
                    "scale_validation.py"
                ),
                (
                    "multi_model_"
                    "intelligence_council.py"
                ),
                (
                    "test_group_batch8e_"
                    "multi_model_council.py"
                ),
                "app.py",
            ],
            backend,
        )

        print(
            "\n=== BATCH 8F + "
            "REGRESSION TESTS ==="
        )
        run(
            [
                py,
                "-m",
                "unittest",
                "-v",
                (
                    "test_group_batch8f_"
                    "scale_validation.py"
                ),
                (
                    "test_group_batch8e_"
                    "multi_model_council.py"
                ),
                (
                    "test_group_batch8d_"
                    "kimi_research.py"
                ),
                (
                    "test_group_batch8c_"
                    "production_inputs.py"
                ),
                (
                    "test_group_batch8b_"
                    "live_sources.py"
                ),
                (
                    "test_group_batch8a_"
                    "jesse_intelligence.py"
                ),
                (
                    "test_group_batch7_"
                    "factory_genericization.py"
                ),
                (
                    "test_group_batch6_"
                    "generic_coverage.py"
                ),
                (
                    "test_governed_chain_"
                    "end_to_end.py"
                ),
            ],
            backend,
        )

        print(
            "\n=== FRONTEND REGRESSION BUILD ==="
        )
        run(
            [npm_command(), "run", "build"],
            frontend,
        )

        print("\n=== INTEGRATION DIFF ===")
        run(["git", "diff", "--stat"], repo)
        run(["git", "status", "-sb"], repo)

        run(
            [
                "git",
                "add",
                "BACK END/backend/app.py",
            ],
            repo,
        )
        run(
            [
                "git",
                "diff",
                "--cached",
                "--check",
            ],
            repo,
        )
        staged = output(
            [
                "git",
                "diff",
                "--cached",
                "--name-only",
            ],
            repo,
        )
        if staged:
            run(
                [
                    "git",
                    "diff",
                    "--cached",
                    "--stat",
                ],
                repo,
            )
            run(
                [
                    "git",
                    "commit",
                    "-m",
                    COMMIT_MESSAGE,
                ],
                repo,
            )
            committed = True
        else:
            print(
                "No new integration diff "
                "to commit."
            )

        # Always push so a retry can recover
        # cleanly after a prior push failure.
        run(
            ["git", "push", "origin", branch],
            repo,
        )

        print("\n=== LIVE BATCH 8F SMOKE ===")
        smoke = run(
            [
                py,
                str(
                    repo
                    / "scripts"
                    / "smoke_batch8f_live.py"
                ),
            ],
            repo,
            check=False,
        )
        if smoke.returncode != 0:
            print(
                "Batch 8F integration is "
                "present, but live smoke "
                "needs attention."
            )
            return smoke.returncode

        print("\n" + "=" * 72)
        print("GROUP BATCH 8F COMPLETE")
        print("IIOS version: 0.19.0")
        print(
            "Bounded scale validation: "
            "INSTALLED"
        )
        print(
            "Task-specific calibration: "
            "INSTALLED"
        )
        print(
            "Minimum sample maturity: "
            "ENFORCED"
        )
        print(
            "Universal model weighting: "
            "FALSE"
        )
        print(
            "Automatic council promotion: "
            "FALSE"
        )
        print(
            "Committee / Risk override: "
            "FALSE"
        )
        print(
            "Capital / trade authority: "
            "FALSE"
        )
        print(
            "Live execution authority: "
            "FALSE"
        )
        print("=" * 72)
        return 0

    except Exception as exc:
        print(
            "Batch 8F apply error: "
            f"{type(exc).__name__}: {exc}"
        )
        if changed and not committed:
            try:
                subprocess.run(
                    [
                        "git",
                        "restore",
                        "--staged",
                        "--",
                        "BACK END/backend/app.py",
                    ],
                    cwd=repo,
                    env=ENV,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                app_path.write_text(
                    original_app,
                    encoding="utf-8",
                )
                print(
                    "Rolled back partial Batch 8F "
                    "app.py integration; working "
                    "tree preserved clean."
                )
            except Exception as rollback_exc:
                print(
                    "Rollback warning:",
                    rollback_exc,
                )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
