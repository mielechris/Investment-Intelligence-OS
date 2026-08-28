# Batch 9J — Outcome Labeling & Learning Memory

## Objective

Turn complete Batch 9H market-validation sessions into governed, review-ready learning memory without changing the running factory.

Batch 9J answers four separate questions:

1. What happened after the market opportunity was first observed?
2. Did IIOS detect it, promote it, WATCH it, reject it, or paper-enter it?
3. How did the eight specialist desks line up with the later market outcome?
4. Which mature examples deserve governed postmortem/Judgment Bank review?

## Forward outcome horizons

For each complete Batch 9H benchmark opportunity, 9J tracks:

- +1 hour
- same-session close
- next trading-session close
- fifth trading-session close

Unavailable future horizons remain `PENDING`. Batch 9J never invents an outcome.

## Decision-quality labels

Market outcome and decision quality are intentionally separate. Examples include:

- `NO_TRADE_FOREGONE_UPSIDE`
- `NO_TRADE_AVOIDED_DOWNSIDE`
- `WATCH_VALIDATED_BY_UPSIDE`
- `WATCH_FALSE_POSITIVE_OR_REVERSAL`
- `FACTORY_MISS_WITH_UPSIDE`
- `PAPER_ENTRY_FAVORABLE`
- `PAPER_ENTRY_ADVERSE`

These are learning labels, not trading signals.

## Agent learning memory

When a benchmark opportunity maps to an IIOS case, 9J reads persisted `agent_result` records through the read-only ledger connection and records each desk's original disposition, confidence, headline, falsifier, and simple outcome alignment.

Agent scorecards are review information only. Batch 9J has no authority to change model or agent weights automatically.

## Judgment Bank boundary

Five-session-mature examples can enter a `judgment_bank_review_queue`, but Batch 9J does not write postmortems or Judgment Bank entries automatically. Governed/human review is required before the existing learning-loop postmortem machinery is used.

## Storage and browser handoff

The sidecar writes:

- per-session `outcome_memory.json`
- `latest_outcome_learning.json`
- browser-ready `browser/outcome_learning.json`

The browser payload uses schema `batch9j-browser-outcome-summary-v1` and is designed for Batch 9K visual integration.

## Runtime

The macOS activation installs `com.iios.outcome-learning` on a one-hour cadence. It uses the existing Batch 9H report directory, Yahoo chart data for forward price observations, and SQLite `mode=ro` for IIOS decision/agent provenance.

Batch 9J fingerprints the existing Batch 9G, 9H, and 9I LaunchAgent plists before installation and verifies they are unchanged afterward.

## Safety

- no live ledger mutation
- no automatic Judgment Bank writes
- no automatic agent-weight changes
- no Committee override
- no Risk override
- no capital authority
- no broker connection
- no live execution
