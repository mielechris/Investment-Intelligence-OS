# Evidence and Reasoning Implementation

## Evidence Creation

Create atomic Evidence from:

- source;
- raw record;
- source span/field;
- availability time;
- quality;
- trust;
- rights.

## Claim Service

Persist:

```text
FACT
INFERENCE
HYPOTHESIS
```

Material facts require evidence before promotion.

## Causal Chain

Each CausalStep requires:

```text
cause
effect
mechanism
sign
lag
evidence OR explicit assumption
falsifier
confidence
```

## Counter-Chain

A promoted thesis requires a credible counter-chain.

## Missing Information

Create explicit requests.

Example:

```text
Question: Has the announced policy been funded?
Why: Implementation depends on appropriated capital.
Blocks promotion: yes
```

## Hypothesis

Require:

- falsifiable statement;
- benchmark;
- expected lag;
- success metric;
- failure metric.

## Thesis

Require:

- instrument;
- disposition;
- horizon;
- catalyst;
- invalidation;
- causal/counter-chain;
- source cutoff.

## Hard Gate

Before thesis promotion:

```python
assert evidence_complete
assert counter_chain_exists
assert invalidation_exists
assert rights_valid
assert critical_data_fresh
```

## Explainability

Build explanation from persisted objects.

Never generate a fresh rationale that is disconnected from stored reasoning.
