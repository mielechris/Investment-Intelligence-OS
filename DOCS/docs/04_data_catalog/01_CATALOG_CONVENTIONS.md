# Data Catalog Conventions

## Identifier Standard

All durable canonical objects use opaque globally unique IDs.

Recommended representation:

```text
id: UUID
```

Provider IDs, tickers, URLs, filing numbers, and names are external identifiers or aliases and MUST NOT be the sole canonical identity.

## Common Metadata

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID | Stable canonical identity |
| `schema_version` | string | Contract version |
| `environment` | enum | DEVELOPMENT, TEST, PAPER, LIVE |
| `created_at` | timestamptz | Creation time |
| `updated_at` | timestamptz | Latest mutable metadata update |
| `created_by` | string/UUID | Human, service, scheduler, or agent |
| `correlation_id` | UUID | End-to-end workflow ID |
| `causation_id` | UUID nullable | Immediate trigger |
| `source_cutoff_at` | timestamptz nullable | Max information cutoff |
| `status` | enum | Object lifecycle |
| `metadata` | JSONB | Non-core extensible metadata |

## Nullability

Null means unknown, not applicable, or not yet determined according to field definition.

Null MUST NOT silently mean zero, false, empty, or no position.

## Money

Authoritative money values use decimal-safe storage and explicit currency.

```text
amount: decimal
currency: string
```

## Prices and Quantities

Use decimal-safe values with instrument-defined:

- tick size;
- price precision;
- quantity precision;
- contract multiplier.

## Percentages

Store normalized decimal values unless otherwise documented.

```text
5.25% → 0.0525
```

## Units

Physical data MUST preserve original and normalized unit context.

Examples:

- barrels;
- metric tons;
- bushels;
- acres;
- millimeters;
- degrees Celsius;
- megawatts;
- basis points.

## Confidence

Canonical confidence values use:

```text
0.0 <= confidence <= 1.0
```

Missing confidence is not equivalent to zero.

## JSONB Policy

JSONB may store provider-specific metadata and sparse optional attributes.

It MUST NOT hide core foreign keys, risk values, portfolio state, timestamps, money, or lineage.
