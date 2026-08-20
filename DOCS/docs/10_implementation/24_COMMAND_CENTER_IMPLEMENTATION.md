# Command Center Implementation

## Today Page Panels

### 1. System Status

Show:

- PAPER;
- current release;
- data cutoff;
- health;
- stand-down.

### 2. World State

- macro regime;
- policy;
- geopolitics;
- weather/commodity;
- market.

### 3. Event Radar

- event;
- source;
- time;
- novelty;
- materiality;
- affected entities;
- state.

### 4. Opportunity Board

- long;
- short;
- watch;
- avoid;
- no-trade;
- horizon;
- confidence;
- risk state.

### 5. Portfolio

- NAV;
- cash;
- exposure;
- drawdown;
- positions;
- causal clusters.

### 6. Learning

- recent postmortems;
- confidence changes;
- retired hypotheses.

## Decision Detail

Implement one drill-down route:

```text
Decision
→ Thesis
→ Causal Chain
→ Claims
→ Evidence
→ Source
→ Agents
→ Dissent
→ Risk
→ Order/Fills
→ Outcome
→ Postmortem
```

## Error States

Every panel needs:

- loading;
- empty;
- stale;
- degraded;
- failed;
- stand-down.

Do not hide stale data behind a normal-looking panel.
