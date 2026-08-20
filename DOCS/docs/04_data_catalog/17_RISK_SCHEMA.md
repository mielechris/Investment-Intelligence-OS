# Risk Schema

---

## `RiskPolicy`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Policy |
| `version` | string | yes | Version |
| `environment` | enum | yes | Environment |
| `single_position_cap` | decimal | yes | Single-position cap |
| `theme_cluster_cap` | decimal | yes | Theme cap |
| `gross_exposure_cap` | decimal | yes | Gross cap |
| `net_exposure_bounds` | JSONB | yes | Net bounds |
| `drawdown_thresholds` | JSONB | yes | Drawdown |
| `stale_data_rules` | JSONB | yes | Stale data |
| `approval_expiry_seconds` | integer | yes | Approval validity |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `RiskAssessment`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Assessment |
| `thesis_id` | UUID | yes | Thesis |
| `committee_decision_id` | UUID | yes | Decision |
| `portfolio_snapshot_id` | UUID | yes | Portfolio |
| `risk_policy_id` | UUID | yes | Policy |
| `market_data_cutoff` | timestamptz | yes | Cutoff |
| `concentration_metrics` | JSONB | yes | Concentration |
| `correlation_metrics` | JSONB | yes | Correlation |
| `liquidity_metrics` | JSONB | yes | Liquidity |
| `drawdown_state` | JSONB | yes | Drawdown |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `RiskDecision`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Decision |
| `assessment_id` | UUID | yes | Assessment |
| `status` | enum | yes | Approval/veto/etc. |
| `max_notional` | decimal | no | Notional cap |
| `max_quantity` | decimal | no | Quantity cap |
| `triggered_rule_ids` | JSONB | no | Rules |
| `reasons` | JSONB | yes | Reasons |
| `expires_at` | timestamptz | yes | Expiry |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
