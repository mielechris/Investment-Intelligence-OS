# Time and Point-in-Time Semantics

IIOS treats time as a first-class data dimension.

## Canonical Time Fields

| Field | Meaning |
|---|---|
| `occurred_at` | When the underlying event happened |
| `transaction_at` | When an underlying transaction occurred |
| `published_at` | When the source published it |
| `effective_at` | When the action became effective |
| `market_available_at` | Earliest reasonable market availability |
| `observed_at` | When IIOS retrieved it |
| `processed_at` | When IIOS transformed it |
| `valid_from` | Start of real-world validity |
| `valid_to` | End of real-world validity |
| `recorded_at` | When IIOS recorded the version |
| `superseded_at` | When a later version replaced it |

## Historical Research Rule

Historical decisions MUST obey:

```text
market_available_at <= simulated_decision_time
```

Later revisions, classifications, or corrections MUST NOT leak backward.

## Disclosure Lag

For delayed public disclosures preserve both:

- underlying event/measurement time;
- public availability time.

Historical signals use public availability.

## Revisions

Macro and other revisable data SHOULD preserve vintage information.

## Bitemporal Objects

Material state SHOULD support both:

- valid time;
- system-known time.

This allows:

- “What was true?”
- “What did IIOS believe at that moment?”

## Timezone Rule

Persist UTC timestamps while retaining original timezone metadata where material.

Naive datetimes MUST NOT enter canonical persistence.
