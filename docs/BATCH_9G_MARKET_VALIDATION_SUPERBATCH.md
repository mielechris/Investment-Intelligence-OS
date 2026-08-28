# Batch 9G — Market Validation Superbatch

## Objective
Move IIOS from runtime-validation into measurable market-validation without touching the live paper-only factory processes.

## Scope
1. Harden Batch 9F telemetry with an explicit heartbeat/freshness contract and paper-fill visibility.
2. Add an end-of-session Opportunity Scorecard that measures what IIOS found, promoted, rejected, missed, and acted on.
3. Add market-validation acceptance metrics for detection latency, promotion rate, Committee/Risk throughput, paper order/fill count, NAV/P&L/drawdown, cadence reliability, and provider/data failure rate.
4. Keep all execution authority unchanged: paper-only, broker disconnected, live capital locked.

## Non-goals
- No broker connectivity.
- No live-capital authority.
- No weakening Committee/Risk gates to manufacture trades.
- No changes to the running 9A/9B/9E processes during development.

## Acceptance
- Telemetry proves it is alive even when no meaningful factory state changes.
- Paper fills are surfaced independently from paper-order creation when the ledger contains them.
- Scorecard can be generated from persisted governed ledger data without mutating the ledger.
- Scorecard records the market opportunity set supplied for evaluation and computes detection/miss metrics reproducibly.
- All new code has compile/tests and explicit no-mutation/no-live-execution CI gates.
