# Canonical Event Schema

---

## `CanonicalEvent`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Event identity |
| `event_type` | string | yes | Canonical event class |
| `title` | string | yes | Human-readable title |
| `summary` | text | no | Structured summary |
| `occurred_at` | timestamptz | no | Underlying event time |
| `published_at` | timestamptz | no | Publication time |
| `effective_at` | timestamptz | no | Effective time |
| `market_available_at` | timestamptz | yes | Point-in-time availability |
| `observed_at` | timestamptz | yes | IIOS retrieval/observation |
| `severity` | decimal | no | Normalized severity |
| `novelty` | decimal | no | Novelty estimate |
| `materiality` | decimal | no | Potential importance |
| `policy_stage` | enum | no | Policy lifecycle where relevant |
| `primary_source_id` | UUID | yes | Primary source |
| `raw_record_id` | UUID | yes | Raw provenance |
| `status` | enum | yes | Lifecycle |
| `revision_of_event_id` | UUID | no | Prior event version |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `EventEntityLink`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `event_id` | UUID | yes | Event |
| `entity_id` | UUID | yes | Entity |
| `role` | string | yes | Role in event |
| `relevance` | decimal | no | Relevance |
| `confidence` | decimal | no | Link confidence |
| `evidence_id` | UUID | no | Evidence |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
