# Hypothesis and Thesis Schema

---

## `Hypothesis`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Hypothesis |
| `version` | integer | yes | Version |
| `title` | string | yes | Title |
| `falsifiable_statement` | text | yes | Testable statement |
| `predicted_direction` | string | yes | Direction |
| `horizon` | string | yes | Horizon |
| `expected_lag` | string | no | Lag |
| `causal_chain_id` | UUID | yes | Primary chain |
| `counter_chain_ids` | JSONB | yes | Counter-cases |
| `benchmark_definition_id` | UUID | yes | Benchmark |
| `success_metric` | JSONB | yes | Success |
| `failure_metric` | JSONB | yes | Failure |
| `status` | enum | yes | Lifecycle |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `InvestmentThesis`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Thesis |
| `hypothesis_id` | UUID | yes | Hypothesis |
| `version` | integer | yes | Version |
| `instrument_id` | UUID | no | Asset expression |
| `disposition` | enum | yes | Long/short/watch/etc. |
| `horizon` | string | yes | Horizon |
| `entry_conditions` | JSONB | no | Entry conditions |
| `catalyst_ids` | JSONB | no | Catalysts |
| `invalidation_conditions` | JSONB | yes | Invalidation |
| `evidence_confidence` | decimal | no | Evidence confidence |
| `causal_confidence` | decimal | no | Causal confidence |
| `implementation_confidence` | decimal | no | Implementation confidence |
| `timing_confidence` | decimal | no | Timing confidence |
| `status` | enum | yes | Status |
| `source_cutoff_at` | timestamptz | yes | Cutoff |
| `expires_at` | timestamptz | no | Expiration |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
