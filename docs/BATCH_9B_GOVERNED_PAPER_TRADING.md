# Batch 9B — Governed Paper Trading

## Objective

Turn the existing IIOS $10,000 governed paper portfolio into an automatically operable mock fund **without adding live-money authority or a broker connection**.

Batch 9B does not create a second decision engine. It advances cases through the existing governed chain and may create a mock position only when the current state passes every pre-existing gate.

## Governed chain

1. Opportunity / case exists in the ledger.
2. Eight specialist desks and Investment Committee have produced a governed decision.
3. Evidence Gap Hunter may deepen at most one WATCH case per 9B cycle.
4. Qualification must persist `qualified_buy_candidate=true`.
5. Existing Thesis state must remain active and unbreached.
6. Existing Capital gate must return `APPROVED` with hard checks and reward/risk passed.
7. Existing deterministic sizing must return `SIZE_READY` with positive whole shares and notional.
8. Existing Paper Authorization API creates or reuses a still-valid single-use `paper_auth_*` token bound to the exact governed state.
9. Batch 9B re-reads the $10K paper portfolio and applies two additional operating guards:
   - no existing position in the same ticker;
   - the authorization's maximum notional must fit inside current available paper cash.
10. Existing Governed Paper Execution API refreshes current market/Capital/sizing state again, verifies the token binding and price window, consumes the token atomically, and records `PAPER_ORDER_CREATED`.
11. Existing paper-portfolio reconciliation ingests that execution and records a marked portfolio snapshot.

## Cadence and limits

- Paper-trading worker cadence: 15 minutes.
- Maximum Evidence Gap Hunts per cycle: 1.
- Maximum new governed paper executions per cycle: 1.
- Evidence Gap retry floor for an unqualified case: 240 minutes.
- Paper entries are attempted only during the regular U.S. equity clock window (09:30–16:00 America/New_York, weekdays). Provider freshness and authorization checks still fail closed on holidays or stale data.

## Safety invariants

- `paper_mode=true`
- broker connected: false
- live execution: false
- live trade execution permission: false
- no broker SDK or broker API is imported
- no arbitrary trade creation
- no Committee override
- no Risk override
- no Capital override
- no sizing override
- no authorization bypass
- no negative-cash paper entry
- no duplicate same-ticker paper entry in Batch 9B v1
- single-use paper authorization remains mandatory

## Operating lanes

Batch 9A Observation Mode stays running in its existing terminal and continues collecting market/event data, creating research cases, monitoring cases, and snapshotting the paper fund.

Batch 9B runs separately in a dedicated terminal. It reads the same governed SQLite ledger through WAL-safe access and advances eligible cases toward paper execution.

Recommended terminal name:

`PAPER TRADING · 9B`

## Acceptance sequence

1. Run the isolated 9B acceptance launcher in dry-run / no-deepening mode against the existing live ledger.
2. Confirm the live Batch8 checkout branch and tracked working-tree state remain unchanged.
3. Confirm the controller classifies existing cases without creating a paper order.
4. Inspect CI and human acceptance.
5. Merge Batch 9B.
6. Start the continuous isolated 9B runner.

## Expected overnight behavior

Outside regular market hours, 9B may deepen a governed WATCH case and persist Qualification state, but it will not create a paper entry. A qualified case waits for the regular-session execution window, at which point Capital, quote freshness, sizing, cash, duplicate exposure, authorization, and execution are all rechecked.

## Empirical goal

Allow the mock $10K account to open its first genuinely governed position only when the complete IIOS evidence-to-capital chain says the case is ready. A zero-position outcome remains valid when no case clears the gates.
