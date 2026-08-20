# Order, Fill, and Execution Schema

---

## `OrderIntent`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Intent |
| `portfolio_id` | UUID | yes | Portfolio |
| `thesis_id` | UUID | yes | Thesis |
| `committee_decision_id` | UUID | yes | Committee |
| `risk_decision_id` | UUID | yes | Risk |
| `instrument_id` | UUID | yes | Instrument |
| `side` | string | yes | Side |
| `target_quantity` | decimal | no | Quantity |
| `target_notional` | decimal | no | Notional |
| `order_type` | string | yes | Order type |
| `time_in_force` | string | yes | TIF |
| `environment` | enum | yes | Environment |
| `idempotency_key` | string | yes | Idempotency |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `PaperOrder`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Order |
| `intent_id` | UUID | yes | Intent |
| `adapter_id` | string | yes | Paper adapter |
| `status` | enum | yes | Status |
| `submitted_quantity` | decimal | yes | Quantity |
| `filled_quantity` | decimal | yes | Filled |
| `average_fill_price` | decimal | no | Average fill |
| `submitted_at` | timestamptz | no | Submit |
| `completed_at` | timestamptz | no | Complete |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `PaperFill`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Fill |
| `order_id` | UUID | yes | Order |
| `instrument_id` | UUID | yes | Instrument |
| `quantity` | decimal | yes | Quantity |
| `price` | decimal | yes | Price |
| `timestamp` | timestamptz | yes | Fill time |
| `spread_cost` | decimal | yes | Spread |
| `slippage_cost` | decimal | yes | Slippage |
| `commission` | decimal | yes | Commission |
| `fees` | decimal | yes | Fees |
| `idempotency_key` | string | yes | Idempotency |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
