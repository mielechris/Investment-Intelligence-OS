# Source and Rights Catalog

---

## `Source`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Canonical source identity |
| `name` | string | yes | Human-readable source |
| `publisher` | string | yes | Publishing organization |
| `source_class` | string | yes | Government, market, research, news, etc. |
| `rights_classification` | enum | yes | Public/licensed/quarantined/prohibited classification |
| `is_primary` | boolean | yes | Whether source is primary |
| `criticality` | string | yes | Operational importance |
| `expected_freshness_seconds` | integer | no | Expected maximum age |
| `owner` | string | yes | Responsible role |
| `status` | string | yes | Operational status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `SourceEndpoint`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Endpoint identity |
| `source_id` | UUID | yes | Parent source |
| `endpoint_type` | string | yes | API/RSS/HTML/file/stream |
| `base_reference` | string | yes | URL/provider reference |
| `auth_method` | string | no | Authentication mechanism |
| `timestamp_semantics` | JSONB | yes | Source time semantics |
| `revision_behavior` | string | yes | How updates/corrections are exposed |
| `is_enabled` | boolean | yes | Operational enablement |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `SourceRightsPolicy`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `source_id` | UUID | yes | Source |
| `use_purpose` | string | yes | Approved purpose |
| `storage_rights` | string | yes | Storage permission |
| `model_processing_allowed` | boolean | yes | Whether AI processing is allowed |
| `retention_rule` | string | yes | Retention policy |
| `export_restrictions` | string | no | Restrictions on export |
| `review_date` | date | yes | Review date |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
