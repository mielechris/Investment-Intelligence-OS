# Investment Committee Implementation

## Required Inputs for Initial Slice

- thesis;
- Policy Analyst output;
- Macro Analyst output;
- Skeptic output;
- explainability packet;
- current world state.

## Session

Create durable `CommitteeSession`.

## Validation

Before debate:

```text
required views present?
evidence complete?
source cutoff known?
critical data healthy?
```

If no:

```text
REQUESTING_EVIDENCE
or
NO_TRADE
```

## Bounded Debate

Maximum:

- configured rounds;
- configured cost;
- configured time.

A new round must add:

- new evidence;
- materially different interpretation;
- or resolution of a blocking issue.

## Decision

Possible:

```text
LONG
SHORT
WATCH
AVOID
NO_TRADE
```

The committee does not size.

## Dissent

Persist every material dissent.

## Expiration

Committee decision expires after configured time or material state change.

## Output

Route candidate to Risk Engine.

No direct order creation.
