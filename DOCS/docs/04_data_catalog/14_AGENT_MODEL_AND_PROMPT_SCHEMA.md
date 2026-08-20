# Agent, Model, and Prompt Schema

---

## `AgentDefinition`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Agent |
| `name` | string | yes | Name |
| `version` | string | yes | Version |
| `mandate` | text | yes | Mandate |
| `permitted_tools` | JSONB | yes | Tool IDs |
| `permitted_source_classes` | JSONB | yes | Source classes |
| `output_schema_version` | string | yes | Output contract |
| `max_steps` | integer | yes | Bound |
| `token_budget` | integer | no | Token limit |
| `cost_budget` | decimal | no | Cost bound |
| `timeout_seconds` | integer | yes | Timeout |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `ModelDefinition`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Model |
| `provider` | string | yes | Provider |
| `model_name` | string | yes | Name |
| `provider_identifier` | string | yes | Exact ID |
| `capabilities` | JSONB | yes | Capabilities |
| `data_use_restrictions` | JSONB | no | Data rules |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `PromptDefinition`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Prompt |
| `version` | string | yes | Version |
| `agent_id` | UUID | yes | Agent |
| `prompt_hash` | string | yes | Content hash |
| `output_schema_version` | string | yes | Output schema |
| `retrieval_policy` | JSONB | yes | Retrieval |
| `tool_policy` | JSONB | yes | Tools |
| `approval_status` | string | yes | Approval |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `AgentRun`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Run |
| `agent_definition_id` | UUID | yes | Agent |
| `model_id` | UUID | yes | Model |
| `prompt_id` | UUID | yes | Prompt |
| `source_cutoff_at` | timestamptz | yes | Cutoff |
| `status` | enum | yes | Status |
| `token_usage` | integer | no | Usage |
| `cost` | decimal | no | Cost |
| `latency_ms` | integer | no | Latency |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
