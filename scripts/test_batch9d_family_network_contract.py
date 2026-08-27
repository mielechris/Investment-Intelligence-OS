#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORTEX = ROOT / "FRONT END" / "src" / "FamilyNetworkCortex.tsx"
SHELL = ROOT / "FRONT END" / "src" / "PaperFundOperationsShell.tsx"

cortex = CORTEX.read_text(encoding="utf-8")
shell = SHELL.read_text(encoding="utf-8")

assert "The Family Network" in cortex
assert "LIVE AGENT CORTEX" in cortex
assert "BOSS'S OFFICE" in cortex
assert "THE SIT-DOWN" in cortex
assert "THE GATE" in cortex
assert "THE VAULT" in cortex
assert "MOTION FOLLOWS LEDGER EVENTS" in cortex
assert "/experience/factory-intelligence/overview" in cortex
assert "/paper-fund/operations" in cortex
assert "AGENT_STARTED" in cortex
assert "AGENT_COMPLETE" in cortex
assert "AGENT_FAILED_CLOSED" in cortex
assert "COMMITTEE_STARTED" in cortex
assert "PaperFundOperationsDock" in shell
assert "FamilyNetworkCortex" in shell

# The cortex is observational only. It cannot run an agent or call a mutating route.
for forbidden in (
    'method: "POST"',
    "method: 'POST'",
    "/submit",
    "/prepare",
    "/run",
    "/mark-to-market",
    "trade_execution_permission: true",
    "live_execution: true",
):
    assert forbidden not in cortex, forbidden

print("PASS: Batch 9D Family Network cortex contract")
