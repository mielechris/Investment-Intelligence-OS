# Golden Trace Implementation

## Purpose

Prove the entire architecture works together.

## Fixture

Use an approved deterministic event fixture.

The exact market outcome is not the point.

The trace must exercise:

```text
source
→ raw record
→ parser
→ canonical event
→ entity
→ evidence
→ claim
→ causal chain
→ counter-chain
→ hypothesis
→ thesis
→ Policy Analyst
→ Macro Analyst
→ Skeptic
→ committee
→ risk
→ paper order or no-trade
→ portfolio
→ journal
→ postmortem
```

## Assertions

Verify:

- every ID links correctly;
- point-in-time cutoff is respected;
- evidence is valid;
- counter-case exists;
- dissent can exist;
- risk can veto;
- no live route;
- replay does not duplicate;
- final journal reconstructs the chain.

## Run Twice

Second execution must not create duplicate:

- raw records;
- canonical effects;
- committee decisions where idempotency applies;
- order intents;
- fills.

## Failure Golden Traces

Create variants for:

- stale source;
- prompt injection;
- risk veto;
- duplicate event;
- worker crash;
- accounting mismatch.
