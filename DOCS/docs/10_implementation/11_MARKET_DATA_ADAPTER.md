# Market Data Adapter

## Purpose

Provide vendor-neutral prices and reference data.

## Internal Protocol

Conceptual interface:

```python
class MarketDataProvider(Protocol):
    def get_instrument(self, external_identifier): ...
    def get_bars(self, instrument_id, start, end, interval): ...
    def get_quote(self, instrument_id): ...
    def get_calendar(self, venue_id): ...
    def get_corporate_actions(self, instrument_id, start, end): ...
```

## Canonicalization

Provider symbols must map to canonical Instrument IDs.

Do not expose provider-specific object types to domain modules.

## Freshness

Every price result carries:

- observation time;
- market-available time;
- source;
- quality status.

## Research

Historical bars must define:

- adjustments;
- survivorship behavior;
- corporate-action policy.

## Paper Execution

Current/delayed quote capability must be declared.

If current data is stale beyond policy:

```text
new risk = disabled
```

## Initial Scope

For the first slice, implement the smallest liquid-instrument subset necessary to demonstrate paper execution.
