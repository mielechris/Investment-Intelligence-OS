# Batch 9A — Observation & Paper Operations

## Objective
Turn IIOS from a build/test environment into a continuously observed, paper-only intelligence factory that accumulates a governed operating history against the existing $10,000 paper portfolio.

## Operating cadence
- Master observation cycle: every 15 minutes.
- Regular-session opportunity discovery: every 30 minutes.
- Off-hours/weekend discovery: every 120 minutes.
- Active monitoring/thesis refresh: existing governed due-profile logic (minimum one hour per profile).
- Paper portfolio: reconcile governed paper executions, fetch governed marks for open positions, record a portfolio snapshot every observation cycle.

## What one cycle does
1. Read the current $10K governed paper portfolio.
2. Refresh monitoring profiles that are due.
3. When discovery is due, run the market-event radar and governed opportunity scan.
4. Promote at most one eligible candidate to a research case.
5. Run a newly promoted case through all eight specialist desks and Investment Committee.
6. Reconcile any already-governed paper executions into the paper portfolio.
7. Fetch governed marks only for positions that already exist.
8. Record a paper-portfolio snapshot and performance history.
9. Persist an `observation_operations_state` checkpoint and `OBSERVATION_CYCLE_COMPLETE` event.

## What Batch 9A does NOT do
- It does not connect to a broker.
- It does not authorize a live order.
- It does not create live capital authority.
- It does not bypass Risk Inspection, qualification, sizing, or paper authorization.
- It does not automatically submit a governed paper execution token.
- It does not lower research/evidence gates to create activity.

## Paper fund
The existing governed paper account remains the accounting authority:
- Starting cash: $10,000.
- Transactions: only from existing `governed_paper_execution` records with `PAPER_ORDER_CREATED`.
- Mark-to-market: governed market quote adapters.
- Live execution: permanently false in Batch 9A.

## Why the first release stops before automatic paper submission
Observation Mode should first prove that opportunity discovery, evidence, eight-desk analysis, Committee behavior, monitoring, and portfolio accounting can operate continuously without fabricating activity. Once we have enough clean observations, Batch 9B can add a tightly governed auto-paper handoff that consumes only valid paper-authorization tokens and still never touches live capital.

## Initial empirical targets
- 50 governed cases.
- 10 governed paper orders.
- 20+ marked paper-portfolio snapshots.
- 5 completed postmortems.
- 10 multi-model/Grok comparison pairs.
- Zero live-execution authority violations.

## Launch modes
One cycle:

```bash
python3 scripts/iios_observation_runner.py --once --force-scan
```

Continuous:

```bash
python3 scripts/iios_observation_runner.py
```

The runner is intentionally a separate process from the Batch Supervisor and API server so it can be stopped or restarted without changing engineering supervision or browser availability.
