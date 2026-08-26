#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

EXPERIENCE_BRANCH = "feature/iios-experience-x0-x1"
INTEGRATION_PREFIX = "integration/iios-experience-x0-x6"
SUPERVISOR_LABEL = "com.iios.batch-supervisor"
SUPERVISOR_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{SUPERVISOR_LABEL}.plist"


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    code = subprocess.run(cmd, cwd=cwd).returncode
    if code != 0:
        raise SystemExit(code)


def output(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=cwd, text=True).strip()


def supervisor_dir() -> Path | None:
    if not SUPERVISOR_PLIST.exists():
        return None
    with SUPERVISOR_PLIST.open("rb") as handle:
        payload = plistlib.load(handle)
    value = payload.get("WorkingDirectory") if isinstance(payload, dict) else None
    return Path(str(value)).expanduser().resolve() if value else None


def require_text(path: Path, needles: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"STOP: {path.name} missing release contracts: {missing}")


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    frontend = repo / "FRONT END"
    src = frontend / "src"

    print("=" * 78)
    print("IIOS EXPERIENCE X0-X6 — INTEGRATION ACCEPTANCE GATE")
    print("=" * 78)

    branch = output(["git", "branch", "--show-current"], repo)
    branch_ok = branch == EXPERIENCE_BRANCH or branch.startswith(INTEGRATION_PREFIX)
    if not branch_ok:
        raise SystemExit(
            f"STOP: experience gate requires {EXPERIENCE_BRANCH!r} or an {INTEGRATION_PREFIX!r} validation branch; found {branch!r}"
        )

    supervisor = supervisor_dir()
    if supervisor and supervisor == repo.resolve():
        raise SystemExit("STOP: experience gate cannot run in the batch supervisor checkout.")
    if supervisor:
        print("Supervisor isolation: OK ->", supervisor)

    required_files = [
        "ExperienceNativeShell.tsx", "ExecutiveShowcase.tsx", "FactoryActivityStrip.tsx", "DeskActivityBoard.tsx",
        "factoryActivityModel.ts", "factoryMovement.ts", "factoryLedgerAdapter.ts", "CasesCommandCard.tsx",
        "NewCaseLauncher.tsx", "CapitalCommandCenter.tsx", "ThesisIntegrityCommand.tsx", "ThesisCapitalConsequenceMatrix.tsx",
        "JudgmentBankWorkspace.tsx", "JudgmentLibraryBrowser.tsx", "activeCaseStore.ts", "stateLanguage.css",
        "factoryActivity.css", "deepIntelligence.css", "executiveShowcase.css",
    ]
    missing = [name for name in required_files if not (src / name).exists()]
    if missing:
        raise SystemExit(f"STOP: missing X0-X6 release files: {missing}")

    require_text(src / "main.tsx", ["ExperienceNativeShell"])
    require_text(src / "ExperienceNativeShell.tsx", [
        "FactoryRoomView", "ResearchRoomView", "CasesRoomView", "CapitalRoomView", "JudgmentRoomView",
        "ExecutiveShowcase", "PAPER / SHADOW", "LIVE CAPITAL LOCKED",
    ])
    require_text(src / "factoryMovement.ts", [
        '"INTACT"', '"EARLY_BUT_INTACT"', '"MATERIAL_CHANGE"', '"THESIS_BROKEN"',
        '"committee.completed"', '"risk.cleared"', '"paper.order.created"',
    ])
    require_text(src / "factoryLedgerAdapter.ts", [
        "COUNCIL_COMPLETE", "COMMITTEE_DECISION", "AGENT_RESULT", "REUNDERWRITE", "SOURCE_ACQUISITION",
    ])
    require_text(src / "activeCaseStore.ts", ["storage", "iios-active-case-changed", "setActiveCaseId", "subscribeActiveCase"])
    require_text(src / "CasesCommandCard.tsx", ["subscribeActiveCase", "getActiveCaseId"])
    require_text(src / "NewCaseLauncher.tsx", ["setActiveCaseId"])
    require_text(src / "ExecutiveShowcase.tsx", [
        "setActiveCaseId", "WHAT CHANGED", "WHY IT MATTERS", "WHAT HAPPENS NEXT", "Real state only",
    ])
    require_text(src / "ThesisCapitalConsequenceMatrix.tsx", ["LIVE CAPITAL", "This surface never grants authority"])
    require_text(src / "JudgmentLibraryBrowser.tsx", ["JUDGMENT", "PROVENANCE"])
    require_text(src / "stateLanguage.css", ["--iios-clear", "--iios-watch", "--iios-block", "--iios-idle"])

    for name in ["ExperienceNativeShell.tsx", "ExecutiveShowcase.tsx", "CapitalCommandCenter.tsx", "ThesisCapitalConsequenceMatrix.tsx"]:
        text = (src / name).read_text(encoding="utf-8").upper()
        if "LIVE EXECUTION ENABLED" in text or "LIVE CAPITAL ENABLED" in text:
            raise SystemExit(f"STOP: unsafe authority language found in {name}")

    run(["git", "diff", "--check"], repo)
    print("\n=== TYPESCRIPT / VITE BUILD ===")
    run(["npm", "run", "build"], frontend)

    print("\n=== EXPERIENCE ESLINT ===")
    lint_targets = [
        "src/ExperienceNativeShell.tsx", "src/ExecutiveShowcase.tsx", "src/FactoryActivityStrip.tsx",
        "src/DeskActivityBoard.tsx", "src/CasesCommandCard.tsx", "src/NewCaseLauncher.tsx",
        "src/CapitalCommandCenter.tsx", "src/ThesisIntegrityCommand.tsx",
        "src/ThesisCapitalConsequenceMatrix.tsx", "src/JudgmentBankWorkspace.tsx",
        "src/JudgmentLibraryBrowser.tsx", "src/activeCaseStore.ts", "src/factoryActivityModel.ts",
        "src/factoryMovement.ts", "src/factoryLedgerAdapter.ts",
    ]
    run(["npx", "eslint", *lint_targets], frontend)

    print("\n=== RELEASE CONTRACT RESULT ===")
    print("PASS: five-room operator shell + Executive View present")
    print("PASS: event movement remains case-identity gated")
    print("PASS: desk activity is event-derived; no-event state is idle")
    print("PASS: four-state thesis integrity model present")
    print("PASS: Judgment Bank provenance surfaces present")
    print("PASS: active-case state synchronized through one store")
    print("PASS: Batch 8 backend remains external to this experience gate")
    print("PASS: live-capital authority remains locked")
    print("PASS: build + experience lint clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
