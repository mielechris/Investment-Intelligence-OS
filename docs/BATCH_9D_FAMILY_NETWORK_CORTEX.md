# Batch 9D — The Family Network / Live Agent Cortex

## Purpose

Add a mob-themed, brain-like live network visualization to IIOS that makes the operating system feel alive **without manufacturing activity**.

## Product rule

The animation is telemetry-bound:

- slow breathing / rotor movement means the 9A or 9B operating engines are online and on cadence;
- bright moving signal packets appear only when recent governed ledger events exist;
- an agent may show `WORKING` only when an explicit `AGENT_STARTED` event exists inside the active telemetry window;
- `JUST FINISHED` is driven by `AGENT_COMPLETE`;
- failed-closed / veto / no-trade states render red;
- idle agents remain dim and labeled `ARMED`;
- offline feeds stop the network.

No fake READY / BUSY / THINKING state is allowed.

## Theme

The canonical IIOS agent identities remain unchanged. The cortex adds display aliases only:

- Policy Analyst → `Policy Crew`
- Macro & Rates → `The Banker`
- Fundamentals → `The Books`
- Market Structure → `The Tape`
- Commodities → `The Supplier`
- Geopolitics & Weather → `The Scout`
- Skeptic / Red Team → `Consigliere`
- Portfolio Context → `The Treasurer`

Downstream governed rooms use theme labels while preserving their real function:

- Current Objective → `BOSS'S OFFICE`
- Committee → `THE SIT-DOWN`
- Risk → `THE GATE`
- Capital → `THE VAULT`
- Paper Execution → `THE BOOK`

These are visual aliases only. Committee, Risk and Capital remain authoritative.

## Data sources

The browser uses existing read-only contracts:

- `GET /experience/factory-intelligence/overview`
- `GET /paper-fund/operations`

The cortex polls these contracts every two seconds and derives movement from the latest audit events already persisted in the governed ledger.

## Motion states

- `THINKING` — explicit in-flight start telemetry exists.
- `SIGNAL FLOW` — recent agent/committee/risk/capital/paper events are arriving.
- `ENGINE IDLE` — 9A/9B are online and on cadence, but no current desk event exists.
- `STANDBY` — browser is connected but the operating engines are not currently on cadence.
- `OFFLINE` — read-only telemetry is unavailable.

## Safety

Batch 9D is observational UI only.

It does not:

- run an agent;
- create a case;
- deepen research;
- prepare paper authorization;
- submit a paper order;
- mark or snapshot the portfolio;
- connect a broker;
- create live execution authority.

## Isolated preview

- preview API: `127.0.0.1:8005`
- preview UI: `127.0.0.1:5191`
- existing 5175 / 5190 / 8002 / 9A / 9B lanes remain untouched.
