#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "BACK END" / "backend" / "governed_paper_execution_api.py"
DOCK = ROOT / "FRONT END" / "src" / "PaperFundOperationsDock.tsx"
SHELL = ROOT / "FRONT END" / "src" / "PaperFundOperationsShell.tsx"
MAIN = ROOT / "FRONT END" / "src" / "main.tsx"

api = API.read_text(encoding="utf-8")
dock = DOCK.read_text(encoding="utf-8")
shell = SHELL.read_text(encoding="utf-8")
main = MAIN.read_text(encoding="utf-8")

assert '@router.get(\n    "/paper-fund/operations"' in api
assert "build_paper_fund_operations" in api
assert "build_portfolio_state" in api
assert "build_performance_history" in api
assert "observation_operations_state" in api
assert "governed_paper_trading_state" in api
assert "governed_paper_execution" in api
assert '"broker_connected": False' in api
assert '"live_capital_locked": True' in api
assert '"trade_execution_permission": False' in api
assert '"live_execution": False' in api

assert "PaperFundOperationsDock" in shell
assert "FactoryIntelligenceExperienceShell" in shell
assert "PaperFundOperationsShell" in main
assert "/paper-fund/operations" in dock
assert "BROKER FALSE · LIVE FALSE" in dock
assert "No trade is manufactured" in dock
assert "Observation Engine" in dock
assert "Governed Paper Trading" in dock
assert "GOVERNED CASE JOURNEY" in dock

# The browser board is observational. It must not call mutating routes.
for forbidden in (
    "/submit",
    "/prepare",
    "/run",
    "/mark-to-market",
    "method: \"POST\"",
    "method: 'POST'",
):
    assert forbidden not in dock, forbidden

print("PASS: Batch 9C Paper Fund Operations UI contract")
