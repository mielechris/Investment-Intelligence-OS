# Portfolio and Position Schema

---

## `Portfolio`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Portfolio |
| `name` | string | yes | Name |
| `environment` | enum | yes | Environment |
| `base_currency` | string | yes | Currency |
| `benchmark_instrument_id` | UUID | no | Benchmark |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `PaperAccount`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Account |
| `portfolio_id` | UUID | yes | Portfolio |
| `broker_adapter_id` | string | yes | Paper adapter |
| `starting_cash` | decimal | yes | Starting cash |
| `current_cash` | decimal | yes | Current cash |
| `reserved_cash` | decimal | yes | Reserved cash |
| `currency` | string | yes | Currency |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Position`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Position |
| `portfolio_id` | UUID | yes | Portfolio |
| `instrument_id` | UUID | yes | Instrument |
| `side` | string | yes | Long/short |
| `quantity` | decimal | yes | Quantity |
| `average_cost` | decimal | yes | Cost |
| `realized_pnl` | decimal | yes | Realized P&L |
| `unrealized_pnl` | decimal | yes | Unrealized P&L |
| `thesis_id` | UUID | yes | Thesis |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `PortfolioSnapshot`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Snapshot |
| `portfolio_id` | UUID | yes | Portfolio |
| `as_of` | timestamptz | yes | As-of |
| `nav` | decimal | yes | NAV |
| `cash` | decimal | yes | Cash |
| `gross_exposure` | decimal | yes | Gross |
| `net_exposure` | decimal | yes | Net |
| `drawdown` | decimal | yes | Drawdown |
| `exposure_breakdowns` | JSONB | yes | Sector/theme/etc. |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
