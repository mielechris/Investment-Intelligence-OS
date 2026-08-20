# Seven-Day Build Sequence

This sequence maps directly to Package 09 tickets.

## Day 1 — Foundation

Goal:

```text
repo + backend + config + postgres + object store + jobs + health
```

Do not proceed until:

- system boots;
- database migrates;
- PAPER guard works;
- secret scan works.

## Day 2 — Ingestion

Goal:

```text
three source categories + market data
→ raw
→ canonical
```

Do not proceed until:

- raw replay works;
- duplicates are idempotent;
- quarantine works.

## Day 3 — World Model and Reasoning

Goal:

```text
event
→ entities
→ evidence
→ causal chain
→ counter-chain
→ hypothesis
→ thesis
```

Do not proceed until:

- historical cutoff works;
- policy stage works;
- missing evidence blocks promotion.

## Day 4 — AI Committee

Goal:

```text
Policy
Macro
Skeptic
→ Committee
```

Do not proceed until:

- injection test passes;
- citations validate;
- no-trade works.

## Day 5 — Risk and Paper

Goal:

```text
Committee
→ Risk
→ Paper
→ Portfolio
```

Do not proceed until:

- veto blocks order;
- accounting reconciles;
- kill switch works.

## Day 6 — Research and UI

Goal:

```text
event study + basic backtest + Today page + decision detail
```

## Day 7 — Golden Trace

Goal:

```text
one complete auditable vertical slice
```

Then freeze, review, and fix.

Do not celebrate breadth before this works.
