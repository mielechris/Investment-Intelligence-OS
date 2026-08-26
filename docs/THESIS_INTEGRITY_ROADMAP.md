# IIOS Thesis Integrity Roadmap

## Core Principle

**Thesis over price.**

A position or research case is not considered wrong merely because price moves against it. Price deterioration may trigger review, but only governed evidence that contradicts the investment thesis can invalidate the thesis.

This principle comes from the distinction between being **wrong** and being **early**.

## Objective

Extend the existing Thesis Lifecycle and invalidation architecture into a generic, multi-company **Thesis Integrity Engine** that tracks whether the original reasons for an investment case remain valid over time.

## Required States

Every monitored case should resolve to one of these governed states:

- `INTACT` — core thesis remains supported.
- `EARLY_BUT_INTACT` — price performance is adverse, but the thesis remains supported and catalysts/timing remain plausible.
- `MATERIAL_CHANGE` — meaningful evidence changed and targeted re-underwriting is required.
- `THESIS_BROKEN` — one or more explicit falsifiers or material thesis assumptions have failed.
- `INSUFFICIENT_EVIDENCE` — the system cannot honestly determine thesis status.
- `CLOSED` — thesis lifecycle is complete.

## Thesis Contract

At initial underwriting, persist a structured thesis contract containing:

- investment thesis summary
- key supporting assumptions
- primary catalysts
- expected time horizon
- explicit falsifiers
- required evidence lanes
- major risks
- sector / macro dependencies
- policy / tariff dependencies when relevant
- institutional-research dependencies when relevant
- valuation assumptions
- confidence at initiation

The contract must be immutable except through a governed re-underwrite that creates a new version and preserves full history.

## Wrong vs. Early Logic

Price alone must never set `THESIS_BROKEN`.

A large drawdown may:

1. trigger a targeted re-underwrite,
2. increase monitoring frequency,
3. request new evidence,
4. route the case to Skeptic and Market Structure,
5. reduce confidence when justified,

but the final classification must depend on whether the original thesis assumptions or falsifiers were actually violated.

### Example

A company may be down 40% after entry while:

- revenue growth remains intact,
- balance sheet remains strong,
- demand/catalyst thesis remains intact,
- policy environment remains supportive,
- no explicit falsifier has triggered.

That case may be `EARLY_BUT_INTACT`, not automatically wrong.

Conversely, a stock can be up while the underlying thesis has deteriorated; positive price action must not override a genuine thesis break.

## Evidence Delta Engine

Each monitoring cycle should compare new governed evidence with the prior thesis contract and prior monitoring snapshot.

Track:

- supporting evidence added
- conflicting evidence added
- assumptions strengthened
- assumptions weakened
- falsifiers triggered
- catalysts achieved / delayed / failed
- financial-quality deterioration
- sector-regime changes
- Fed / macro regime changes
- tariff / policy transmission changes
- institutional sentiment changes
- valuation regime changes
- price performance as context only

## Thesis Integrity Score

Produce a bounded score for monitoring and UI purposes, with transparent components rather than an opaque LLM score.

Suggested components:

- Fundamental integrity
- Catalyst integrity
- Balance-sheet / liquidity integrity
- Competitive-position integrity
- Sector / demand integrity
- Macro / monetary-policy integrity
- Policy / tariff integrity
- Valuation integrity
- Institutional-consensus divergence
- Evidence freshness / quality

The score cannot authorize a trade or override explicit falsifiers.

## Time-Horizon Awareness

A thesis must be judged against its intended horizon.

Examples:

- next-day tactical dislocation
- weeks-to-months swing thesis
- 6–18 month fundamental thesis
- multi-year infrastructure / secular thesis

The system should not call a long-duration thesis wrong merely because short-term price action is adverse. At the same time, a tactical thesis that misses its defined window should be treated as a failed or expired thesis unless explicitly re-underwritten.

## Required Review Triggers

Targeted re-underwriting should occur when any of the following happen:

- explicit falsifier triggered
- material earnings / guidance change
- major balance-sheet deterioration
- catalyst materially delayed or cancelled
- major regulatory / tariff / policy change
- meaningful sector-regime reversal
- material institutional-consensus reversal
- significant price drawdown beyond case-specific threshold
- evidence conflict above governed threshold
- evidence becomes stale
- investment horizon expires

Price drawdown is a review trigger, not an automatic invalidation.

## Agent Routing

- Fundamentals: financial / operating thesis integrity
- Macro: rates, inflation, credit, monetary-policy regime
- Policy: tariffs, regulation, subsidies, export controls
- Market Structure: price / liquidity / positioning anomalies
- Commodities: input-cost and commodity dependencies
- Geo / Weather: geopolitical and physical-supply risks
- Skeptic: strongest case that the thesis is actually broken
- Portfolio: portfolio-level consequences and concentration

The Committee synthesizes the evidence and preserves dissent.

## UI / Factory Room

Add a **Thesis Integrity Room** showing:

- current state
- original thesis
- thesis age / intended horizon
- current return
- integrity score
- catalysts status
- active watches
- triggered falsifiers
- supporting vs. conflicting evidence
- confidence history
- `WRONG` vs `EARLY` classification
- next required evidence
- last re-underwrite

Price should be visually separated from thesis integrity so users do not conflate P&L with thesis correctness.

## Learning / Judgment Bank

Postmortems should evaluate two distinct questions:

1. Was the thesis reasoning correct?
2. Was the entry / timing / sizing correct?

This separation is required so IIOS can learn from cases where:

- thesis right, timing wrong
- thesis wrong, price temporarily favorable
- thesis right, catalyst slower than expected
- thesis right, sizing inappropriate
- thesis broken and correctly exited / rejected

## Governance

- Paper / shadow only until separately approved.
- No price-only automatic sell.
- No automatic live execution.
- No LLM-only thesis invalidation.
- Explicit falsifiers and governed evidence must drive hard invalidation.
- Full thesis-version lineage must be preserved.

## Roadmap Placement

1. Finish Group Batch 7 — Factory Genericization + Evidence Precision.
2. Extend the generic monitoring architecture with this Thesis Integrity Engine.
3. Integrate Institutional Research, Cross-Sector Sentiment, Monetary Policy Probability / Historical Reaction, and Tariff Transmission as additional evidence lanes.
4. Feed the Daily Dislocation Scanner into the same thesis-contract framework, using a much shorter tactical horizon.
5. Validate wrong-vs-early classifications during the 50-case validation program and paper portfolio postmortems.
