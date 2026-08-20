# Research Run and Result Schema

---

## `ResearchRun`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Run |
| `run_type` | string | yes | Event study/backtest/etc. |
| `strategy_id` | UUID | no | Strategy |
| `dataset_manifest_id` | UUID | yes | Dataset |
| `parameter_set` | JSONB | yes | Parameters |
| `random_seed` | integer | no | Seed |
| `code_commit` | string | yes | Code |
| `dependency_lock_hash` | string | yes | Dependencies |
| `started_at` | timestamptz | yes | Start |
| `completed_at` | timestamptz | no | Finish |
| `status` | string | yes | Status |
| `result_hash` | string | no | Result hash |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `ResearchResult`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `research_run_id` | UUID | yes | Run |
| `gross_return` | decimal | no | Gross |
| `net_return` | decimal | no | Net |
| `benchmark_return` | decimal | no | Benchmark |
| `volatility` | decimal | no | Volatility |
| `max_drawdown` | decimal | no | Drawdown |
| `hit_rate` | decimal | no | Hit rate |
| `turnover` | decimal | no | Turnover |
| `sample_size` | integer | yes | Observations |
| `cost_sensitivity` | JSONB | no | Cost sensitivity |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
