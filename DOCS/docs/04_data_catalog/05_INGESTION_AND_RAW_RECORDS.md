# Ingestion and Raw Record Catalog

---

## `RetrievalAttempt`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Attempt ID |
| `source_endpoint_id` | UUID | yes | Source endpoint |
| `connector_id` | string | yes | Connector/version |
| `started_at` | timestamptz | yes | Start |
| `completed_at` | timestamptz | no | Completion |
| `provider_request_id` | string | no | External request ID |
| `success` | boolean | yes | Whether retrieval succeeded |
| `error_class` | string | no | Normalized error |
| `attempt_number` | integer | yes | Retry attempt |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `RawRecord`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Raw record ID |
| `source_id` | UUID | yes | Source |
| `source_native_id` | string | no | Provider native ID |
| `revision_id` | string | no | Provider revision ID |
| `content_hash` | string | yes | Immutable content hash |
| `media_type` | string | yes | MIME/media type |
| `object_uri` | string | yes | Object-store reference |
| `published_at` | timestamptz | no | Publication |
| `effective_at` | timestamptz | no | Effective time |
| `market_available_at` | timestamptz | no | Market availability |
| `observed_at` | timestamptz | yes | IIOS observation |
| `rights_classification` | enum | yes | Rights class |
| `status` | enum | yes | Lifecycle status |
| `supersedes_raw_record_id` | UUID | no | Previous raw version |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `ParseResult`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Parse run |
| `raw_record_id` | UUID | yes | Source raw record |
| `parser_id` | string | yes | Parser |
| `parser_version` | string | yes | Parser version |
| `structured_payload` | JSONB | no | Parsed representation |
| `warnings` | JSONB | no | Warnings |
| `confidence` | decimal | no | Extraction confidence |
| `status` | string | yes | Parse status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `ConnectorCheckpoint`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `connector_id` | string | yes | Connector |
| `source_endpoint_id` | UUID | yes | Endpoint |
| `checkpoint_type` | string | yes | Cursor/time/hash type |
| `checkpoint_value` | string | yes | Durable cursor |
| `updated_at` | timestamptz | yes | Checkpoint time |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
