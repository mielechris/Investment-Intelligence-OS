# Research Dataset and Strategy Schema

---

## `DatasetManifest`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Dataset |
| `version` | string | yes | Version |
| `purpose` | text | yes | Purpose |
| `source_versions` | JSONB | yes | Sources |
| `rights_classification` | JSONB | yes | Rights |
| `cutoff_rules` | JSONB | yes | Point-in-time rules |
| `universe_definition` | JSONB | yes | Universe |
| `corporate_action_policy` | JSONB | yes | Corporate actions |
| `revision_policy` | JSONB | yes | Revisions |
| `feature_versions` | JSONB | yes | Features |
| `label_versions` | JSONB | yes | Labels |
| `content_hash` | string | yes | Hash |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `FeatureDefinition`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Feature |
| `version` | string | yes | Version |
| `name` | string | yes | Name |
| `formula_reference` | string | yes | Transformation |
| `required_sources` | JSONB | yes | Sources |
| `cutoff_rule` | JSONB | yes | Cutoff |
| `missing_data_rule` | JSONB | yes | Missing data |
| `leakage_test` | string | yes | Leakage test |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `StrategyDefinition`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Strategy |
| `version` | string | yes | Version |
| `hypothesis_id` | UUID | yes | Hypothesis |
| `name` | string | yes | Name |
| `universe_rule` | JSONB | yes | Universe |
| `signal_definition` | JSONB | yes | Signal |
| `exit_logic` | JSONB | yes | Exit |
| `benchmark_id` | UUID | yes | Benchmark |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
