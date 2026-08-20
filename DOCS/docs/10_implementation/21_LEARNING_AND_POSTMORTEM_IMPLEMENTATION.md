# Learning and Postmortem Implementation

## Trigger

Postmortem runs when:

- thesis closes;
- thesis invalidates;
- horizon expires;
- major incident affects the decision.

## Inputs

- original thesis;
- causal chain;
- committee;
- risk;
- fills;
- portfolio;
- realized market path;
- source revisions;
- model outputs.

## Required Questions

1. What did we expect?
2. What happened?
3. Which causal steps occurred?
4. Which did not?
5. Was timing wrong?
6. Was evidence wrong?
7. Was risk wrong?
8. Was execution wrong?
9. Was the result luck?

## Process / Outcome Matrix

```text
good process + good outcome
good process + bad outcome
bad process + good outcome
bad process + bad outcome
```

## Belief Update

Learning can propose:

- confidence increase/decrease;
- new falsifier;
- new missing-information requirement;
- pause;
- retirement.

It cannot automatically:

- change Constitution;
- change risk policy;
- deploy new model;
- enable live execution.
