# Instrument and Market Reference Schema

---

## `Instrument`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Instrument identity |
| `instrument_type` | string | yes | Equity/ETF/option/future/FX/crypto/etc. |
| `canonical_symbol` | string | no | Display symbol |
| `issuer_entity_id` | UUID | no | Issuer |
| `underlying_instrument_id` | UUID | no | Underlying |
| `venue_id` | UUID | no | Trading venue |
| `trading_currency` | string | yes | Currency |
| `contract_multiplier` | decimal | no | Multiplier |
| `tick_size` | decimal | no | Minimum price increment |
| `listing_date` | date | no | Listing |
| `expiry_date` | date | no | Expiry |
| `strike` | decimal | no | Option strike |
| `option_type` | string | no | CALL/PUT |
| `status` | string | yes | Status |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `InstrumentIdentifier`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `instrument_id` | UUID | yes | Instrument |
| `namespace` | string | yes | Ticker/ISIN/FIGI/provider |
| `identifier` | string | yes | Value |
| `venue_id` | UUID | no | Venue |
| `valid_from` | timestamptz | no | Validity |
| `valid_to` | timestamptz | no | Validity |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `Venue`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Venue |
| `name` | string | yes | Name |
| `code` | string | yes | Code |
| `country_code` | string | no | Country |
| `timezone` | string | yes | Timezone |
| `market_calendar_id` | UUID | yes | Calendar |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.

## `MarketCalendar`

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `id` | UUID | yes | Calendar |
| `timezone` | string | yes | Timezone |
| `regular_sessions` | JSONB | yes | Sessions |
| `holidays` | JSONB | yes | Holidays |
| `continuous_market` | boolean | yes | 24/7 flag |

### Object Rules

- Uses the global Data Catalog conventions.
- Material versions preserve history rather than overwrite prior state.
- Point-in-time fields must follow `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`.
- Authoritative writes belong to the owning module.
- Validation and persistence tests are required.
