# Batch 9G — Market Validation Superbatch

## Objective
Move IIOS from runtime-validation into measurable market-validation without touching the live paper-only factory processes.

## Scope
1. Harden Batch 9F telemetry with an explicit heartbeat/freshness contract and governed paper-fill visibility.
2. Add an end-of-session Opportunity Scorecard that measures what IIOS found, promoted, rejected, missed, and acted on.
3. Add market-validation acceptance metrics for detection latency, detection/miss rate, promotion rate, Committee/Risk throughput, paper order/fill count, NAV/P&L/drawdown, cadence reliability, and provider/data failure count.
4. Keep all execution authority unchanged: paper-only, broker disconnected, live capital locked.

## Architecture
- `factory_telemetry.py` remains the verified Batch 9F baseline.
- `factory_telemetry_v2.py` extends that read-only snapshot with paper fills sourced only from persisted `paper_portfolio_transaction` objects.
- `iios_factory_telemetry_exporter_v2.py` preserves the meaningful-state fingerprint and refreshes the private telemetry sink on a five-minute heartbeat even when factory state is unchanged.
- `market_validation_scorecard.py` compares a supplied end-of-session market opportunity set with persisted IIOS candidates and their downstream lineage.
- `iios_market_validation_scorecard.py` writes the reproducible scorecard to local JSON or stdout; it never writes to the IIOS ledger.

## Paper fill semantics
A Batch 9G paper fill is not a broker/exchange fill. It is a persisted governed paper-portfolio transaction created from a completed `PAPER_ORDER_CREATED` execution by the existing paper portfolio reconciliation path. The telemetry label is `CONFIRMED_PAPER_FILL`, with provenance `PERSISTED_GOVERNED_PAPER_TRANSACTION`.

## Opportunity-set input
The scorecard accepts JSON with:
- `session_id`
- ISO `session_start`
- ISO `session_end`
- `benchmark_complete` (true only when the supplied opportunity set is intended to be exhaustive)
- `opportunities[]` with `ticker`, ISO `event_at`, and optional `opportunity_id`, `label`, `move_pct`, `importance`, and `source`

A false-positive rate is reported only when `benchmark_complete=true`; otherwise the scorecard reports unmatched IIOS candidate tickers without claiming they were false positives.

## Core metrics
- opportunity count
- detected count and detection rate
- missed count and opportunity miss rate
- average/median detection latency
- promoted count and promotion rate of detected opportunities
- Committee and Risk throughput
- paper orders and governed paper fills
- paper-fill rate of orders
- unmatched factory candidate tickers
- false-positive rate only for complete benchmarks
- current cadence reliability
- provider error count
- paper NAV, total P&L, current drawdown, and max drawdown

## Safety
- SQLite ledger access remains `mode=ro`.
- No broker connectivity is added.
- No Committee, Risk, or capital override is added.
- No live-capital authority is added.
- No gate is weakened to manufacture a trade.
- No running 9A/9B/9E process is changed by branch development.

## Acceptance
- Telemetry proves it is alive even when no meaningful factory state changes.
- Paper fills are surfaced independently from paper-order creation when the governed paper ledger contains them.
- Scorecard can be generated from persisted governed ledger data without mutating the ledger.
- Scorecard records the supplied market opportunity set and computes detection/miss metrics reproducibly.
- Incomplete external benchmarks do not produce a misleading false-positive rate.
- All new code has compile/tests and explicit no-mutation/no-live-execution CI gates.

## Example
```bash
python scripts/iios_market_validation_scorecard.py \
  --input runtime/market_opportunities_2026-08-28.json \
  --db "BACK END/backend/iios_ledger.db" \
  --output runtime/market_validation_scorecard_2026-08-28.json
```

The `runtime/` artifacts remain local-only and should not be committed.
