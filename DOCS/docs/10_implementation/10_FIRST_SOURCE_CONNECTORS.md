# First Source Connectors

The first vertical slice needs three source categories plus market data.

## Connector A — Presidency / Federal Policy

Implement one official primary-source connector capable of retrieving:

- presidential actions;
- executive orders;
- official remarks;
- memoranda/proclamations;
- other approved official policy publications.

Canonical output must distinguish:

- remark;
- meeting;
- announced intent;
- formal action.

## Connector B — Federal Reserve / Macro

Implement one primary connector for:

- Federal Reserve events;
- or another approved macro source required by the slice.

Preserve:

- publication time;
- release value;
- revision/vintage logic.

## Connector C — Non-Policy Primary Source

Choose one initial source:

- SEC;
- NOAA;
- USDA;
- EIA;
- CFTC;
- Treasury/OFAC;
- USTR;
- Commerce;
- another approved official source.

## Source Manifest

Before connector code, register:

```text
source ID
publisher
rights classification
freshness
criticality
timestamp semantics
revision behavior
rate limit
parser
retention
```

## Fixture Rule

Every connector gets static approved fixtures so tests do not require live internet.

## Live Fetch Rule

Live fetch is an operational capability; tests must remain deterministic.
