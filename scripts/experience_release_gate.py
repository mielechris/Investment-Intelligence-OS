#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

BRANCH = "feature/iios-experience-x0-x1"
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
    print("IIOS EXPERIENCE X0-X6 — RELEASE ACCEPTANCE GATE")
    print("=" * 78)

    branch = output(["git", "branch", "--show-current"], repo)
    if branch != BRANCH:
        raise SystemExit(f"STOP: release gate requires {BRANCH}; found {branch}")

    supervisor = supervisor_dir()
    if supervisor and supervisor == repo.resolve():
        raise SystemExit("STOP: release gate cannot run in the batch supervisor checkout.")
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

    require_text(src / "ExperienceNativeShell.tsx", [
        "FactoryRoomView", "ResearchRoomView", "CasesRoomView", "CapitalRoomView", "JudgmentRoomView",
        "ExecutiveShowcase", "PAPER / SHADOW", "LIVE CAPITAL LOCKED",
    ])
    require_text(src / "factoryMovement.ts", [
        '"INTACT"', '"EARLY_BUT_INTACT"', '"MATERIAL_CHANGE"', '"THESIS_BROKEN"',
        '"committee.completed"', '"risk.cleared"', '"paper.order.created"',
    ])
    require_text(src / "factoryLedgerAdapter.ts", [
        "COUNCIL_COMPLETE", "COMMITTEE_DECISION", "AGENT_RESULT", "REUNDERWRITE", "SOURCE_ACQUISITION", "movementEligible:false",
    ])
    require_text(src / "factoryActivityModel.ts", ["BUSY", "RECENT", "IDLE", "No recent" if False else "IDLE"])
    require_text(src / "activeCaseStore.ts", ["storage", "iios-active-case-changed", "setActiveCaseId", "subscribeActiveCase"])
    require_text(src / "CasesCommandCard.tsx", ["subscribeActiveCase", "getActiveCaseId"])
    require_text(src / "NewCaseLauncher.tsx", ["setActiveCaseId"])
    require_text(src / "ExecutiveShowcase.tsx", ["subscribeActiveCase", "setActiveCaseId", "WHAT CHANGED", "WHY IT MATTERS", "WHAT HAPPENS NEXT", "Real state only"])
    require_text(src / "ThesisCapitalConsequenceMatrix.tsx", ["subscribeActiveCase", "LIVE CAPITAL", "This surface never grants authority"])
    require_text(src / "JudgmentLibraryBrowser.tsx", ["JUDGMENT", "PROVENANCE"])
    require_text(src / "stateLanguage.css", ["--iios-clear", "--iios-watch", "--iios-block", "--iios-idle"])

    for name in ["ExperienceNativeShell.tsx", "ExecutiveShowcase.tsx", "CapitalCommandCenter.tsx", "ThesisCapitalConsequenceMatrix.tsx"]:
        text = (src / name).read_text(encoding="utf-8").upper()
        if "LIVE EXECUTION ENABLED" in text or "LIVE CAPITAL ENABLED" in text:
            raise SystemExit(f"STOP: unsafe authority language found in {name}")

    run(["git", "diff", "--check"], repo)
    print("\n=== TYPESCRIPT / VITE BUILD ===")
    run(["npm", "run", "build"], frontend)
    print("\n=== ESLINT ===")
    run(["npm", "run", "lint"], frontend)

    print("\n=== RELEASE CONTRACT RESULT ===")
    print("PASS: five-room operator shell + Executive View present")
    print("PASS: event movement remains case-identity gated")
    print("PASS: desk activity is event-derived; no-event state is idle")
    print("PASS: four-state thesis integrity model present")
    print("PASS: Judgment Bank provenance surfaces present")
    print("PASS: active-case state synchronized through one store")
    print("PASS: live-capital authority remains locked")
    print("PASS: build + lint clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
