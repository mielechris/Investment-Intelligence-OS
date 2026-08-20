# Committee and Decision Schema

---

## `CommitteeSession`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Session |
| `thesis_id` | UUID | yes | Thesis |
| `world_state_snapshot_id` | UUID | yes | World state |
| `source_cutoff_at` | timestamptz | yes | Cutoff |
| `required_agent_roles` | JSONB | yes | Required views |
| `status` | enum | yes | Status |
| `debate_round_count` | integer | yes | Rounds |
| `expires_at` | timestamptz | no | Expiry |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `DissentRecord`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Dissent |
| `committee_session_id` | UUID | yes | Session |
| `agent_run_id` | UUID | yes | Agent |
| `disputed_statement` | text | yes | Dispute |
| `evidence_ids` | JSONB | no | Evidence |
| `confidence` | decimal | no | Confidence |
| `risk_critical` | boolean | yes | Risk critical |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `CommitteeDecision`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Decision |
| `session_id` | UUID | yes | Session |
| `thesis_id` | UUID | yes | Thesis |
| `disposition` | enum | yes | Disposition |
| `rationale` | text | yes | Rationale |
| `strongest_support_evidence_ids` | JSONB | no | Support |
| `strongest_contradiction_evidence_ids` | JSONB | no | Contradiction |
| `confidence_dimensions` | JSONB | yes | Confidence |
| `expires_at` | timestamptz | no | Expiry |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
