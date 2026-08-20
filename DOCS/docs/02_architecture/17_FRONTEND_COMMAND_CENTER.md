# Investment Intelligence OS
## Frontend and Command Center Architecture — v0.1

---

## 1. Frontend Mission

The command center helps one operator understand the system in approximately ten minutes without hiding uncertainty or risk.

It is a decision-review interface, not a slot-machine interface.

---

## 2. Frontend Architecture

V1 uses a typed React frontend.

The frontend communicates only with the versioned API.

Authoritative calculations remain in the backend.

---

## 3. Primary Navigation

Recommended sections:

1. Today
2. Events
3. World State
4. Evidence
5. Hypotheses and Theses
6. Committee
7. Portfolio and Risk
8. Research
9. Decision Journal
10. System Health
11. Settings

---

## 4. Today Page

The default page contains:

### System Banner

- environment;
- data cutoff;
- paper/live status;
- stand-down state;
- critical alerts.

### World State

- macro regime;
- policy state;
- geopolitical state;
- weather and commodity state;
- market state.

### Event Radar

- ranked new events;
- novelty;
- materiality;
- affected entities;
- source quality;
- current processing stage.

### Opportunity Board

- long;
- short;
- watch;
- avoid;
- no-trade;
- horizon;
- confidence dimensions;
- risk status.

### Portfolio

- NAV;
- cash;
- gross and net exposure;
- drawdown;
- theme exposure;
- open positions;
- invalidation alerts.

### Learning

- recent postmortems;
- agent calibration;
- strategy changes;
- retired assumptions.

---

## 5. Decision Detail Page

A decision detail page shows:

- thesis;
- event context;
- facts;
- inferences;
- causal chain;
- counter-chain;
- evidence;
- source documents;
- agent views;
- dissent;
- committee decision;
- risk decision;
- order and fills;
- outcome;
- postmortem;
- all versions.

The user must be able to navigate backward to the original source.

---

## 6. Visual Language

Required visible states:

- healthy;
- stale;
- incomplete;
- quarantined;
- conflicting;
- no-trade;
- risk veto;
- stand-down;
- paper mode.

Do not rely on color alone.

Text labels and icons must explain state.

---

## 7. Data Freshness

Each panel displays:

- as-of time;
- source cutoff;
- stale warning;
- refresh status;
- failed sources affecting the panel.

A fresh-looking page with stale data is prohibited.

---

## 8. Server State

The frontend treats API data as server state.

Use a query layer that supports:

- caching;
- invalidation;
- retries;
- loading state;
- error state;
- polling or streaming;
- request deduplication.

Cache does not hide stale backend metadata.

---

## 9. Local UI State

Local state may contain:

- selected filters;
- open panels;
- sorting;
- draft notes;
- display preferences.

It may not contain authoritative:

- positions;
- risk limits;
- decisions;
- orders;
- portfolio P&L;
- source trust.

---

## 10. Charts

Charts must include:

- units;
- timeframe;
- source;
- cutoff;
- benchmark;
- event markers where relevant;
- missing-data indication.

Charts may not imply certainty through decorative precision.

---

## 11. Evidence Graph View

The graph view should allow:

- source-to-claim lineage;
- support and contradiction;
- entity relationships;
- causal chain;
- thesis and decision;
- outcome.

Large graphs are filtered by context rather than rendered as an unreadable universe.

---

## 12. Accessibility

The command center should support:

- keyboard navigation;
- readable contrast;
- labeled controls;
- semantic headings;
- screen-reader-friendly tables;
- non-color status cues;
- responsive layout.

---

## 13. Error States

Every panel needs:

- loading;
- empty;
- stale;
- partial;
- failed;
- unauthorized;
- stand-down.

A failed panel does not silently display old state as current.

---

## 14. Actions

Privileged actions require confirmation where appropriate:

- activate stand-down;
- resume from stand-down;
- cancel workflow;
- change risk policy;
- delete or quarantine source;
- promote strategy;
- export audit bundle.

V1 live execution action does not exist.

---

## 15. Frontend Observability

Record:

- page-load errors;
- API failures;
- slow queries;
- unhandled exceptions;
- correlation IDs;
- build version.

Do not record secrets or sensitive source contents unnecessarily.

---

## 16. Frontend Acceptance Tests

- paper mode is always visible;
- stale data is visually explicit;
- decision detail links to evidence and source;
- browser manipulation cannot alter backend portfolio values;
- no-trade and risk-veto states are understandable;
- failed API produces an error state;
- keyboard navigation works for critical flow;
- frontend build version appears in diagnostics;
- owner can reconstruct one golden-trace decision from the UI.
