# Market Data Schema

---

## `Bar`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `instrument_id` | UUID | yes | Instrument |
| `interval` | string | yes | Bar interval |
| `start_at` | timestamptz | yes | Start |
| `end_at` | timestamptz | yes | End |
| `open` | decimal | yes | Open |
| `high` | decimal | yes | High |
| `low` | decimal | yes | Low |
| `close` | decimal | yes | Close |
| `volume` | decimal | no | Volume |
| `source_id` | UUID | yes | Source |
| `market_available_at` | timestamptz | yes | Availability |
| `adjustment_policy` | string | yes | Adjusted/unadjusted policy |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Quote`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `instrument_id` | UUID | yes | Instrument |
| `timestamp` | timestamptz | yes | Quote time |
| `bid_price` | decimal | no | Bid |
| `bid_size` | decimal | no | Bid size |
| `ask_price` | decimal | no | Ask |
| `ask_size` | decimal | no | Ask size |
| `last_price` | decimal | no | Last |
| `source_id` | UUID | yes | Source |
| `quality_status` | string | yes | Quality |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `MarketObservation`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `series_id` | UUID | yes | Series |
| `timestamp` | timestamptz | yes | Observation |
| `value` | decimal | yes | Value |
| `unit` | string | yes | Unit |
| `source_id` | UUID | yes | Source |
| `market_available_at` | timestamptz | yes | Availability |
| `revision_id` | string | no | Revision |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
