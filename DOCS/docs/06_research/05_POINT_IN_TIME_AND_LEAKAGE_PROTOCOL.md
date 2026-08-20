# Point-in-Time and Leakage Protocol

## Leakage Definition

Leakage occurs when research uses information that would not have been known at the simulated decision time.

## Common Leakage Sources

- revised macro data;
- later SEC filings;
- future index membership;
- survivor-only universes;
- future policy implementation state;
- future earnings restatements;
- future event labels;
- post-event news classification;
- future analyst estimates;
- future model embeddings generated from later text.

## Required Test

For every feature:

```text
feature.market_available_at <= simulated_decision_time
```

## Intentional Leakage Fixtures

The test suite should contain known future-data traps.

The pipeline must fail when they enter features.

## Label Isolation

Outcome labels must be physically or logically separated from feature construction.

## Holdout Isolation

Final holdout access must be logged.

## Publication vs Event Time

Historical features use when the information became public, not merely when the underlying event occurred.

## Leakage Review

Every promoted research run includes a signed-off leakage checklist.
