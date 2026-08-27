#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "BACK END" / "backend" / "governed_paper_execution_api.py"
PREVIEW_API = ROOT / "scripts" / "batch9c_preview_api.py"
DOCK = ROOT / "FRONT END" / "src" / "PaperFundOperationsDock.tsx"
SHELL = ROOT / "FRONT END" / "src" / "PaperFundOperationsShell.tsx"
MAIN = ROOT / "FRONT END" / "src" / "main.tsx"

api = API.read_text(encoding="utf-8")
preview_api = PREVIEW_API.read_text(encoding="utf-8")
dock = DOCK.read_text(encoding="utf-8")
shell = SHELL.read_text(encoding="utf-8")
main = MAIN.read_text(encoding="utf-8")

assert '@router.get(\n    "/paper-fund/operations"' in api
assert "build_paper_fund_operations" in api
assert "PERSISTED_GOVERNED_PAPER_SNAPSHOTS_ONLY" in api
assert "PERSISTED_LEDGER_ONLY" in api
assert "observation_operations_state" in api
assert "governed_paper_trading_state" in api
assert "governed_paper_execution" in api
assert '"broker_connected": False' in api
assert '"live_capital_locked": True' in api
assert '"trade_execution_permission": False' in api
assert '"live_execution": False' in api

# The 9C read model must not use operational portfolio builders that can reconcile
# or create ledger state as a side effect.
assert "build_portfolio_state" not in api
assert "build_performance_history" not in api
assert "reconcile_governed_executions" not in api
assert "record_portfolio_snapshot" not in api

assert "PaperFundOperationsDock" in shell
assert "FactoryIntelligenceExperienceShell" in shell
assert "PaperFundOperationsShell" in main
assert "/paper-fund/operations" in dock
assert "BROKER FALSE · LIVE FALSE" in dock
assert "No trade is manufactured" in dock
assert "Observation Engine" in dock
assert "Governed Paper Trading" in dock
assert "GOVERNED CASE JOURNEY" in dock
assert "NOT_QUALIFIED" in dock
assert "NOT_WATCH" in dock

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

# The isolated preview API exposes only the three read surfaces needed by 9C.
assert "@app.post" not in preview_api
assert "allow_methods=[\"GET\"]" in preview_api
assert "paper_order_route_exposed\": False" in preview_api
assert "trade_execution_permission\": False" in preview_api
assert "live_execution\": False" in preview_api

print("PASS: Batch 9C strict read-only Paper Fund Operations UI contract")
