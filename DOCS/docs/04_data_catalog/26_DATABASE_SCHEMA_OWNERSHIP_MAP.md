# Database Schema Ownership Map

| PostgreSQL Schema | Primary Objects | Owning Module |
|---|---|---|
| `platform` | configuration, identity metadata, releases | Platform |
| `source` | sources, endpoints, rights, health | Source Registry |
| `ingest` | retrieval, raw metadata, parse, normalization, quarantine | Ingestion |
| `market` | instruments, venues, calendars, bars, quotes, curves | Market Data |
| `knowledge` | entities, aliases, relationships, world state, regimes | Knowledge |
| `evidence` | evidence, claims, support/contradiction | Evidence |
| `reasoning` | causal chains, assumptions, falsifiers, hypotheses, theses | Reasoning |
| `agents` | agents, models, prompts, runs, outputs | Agent Runtime |
| `decision` | committee, debate, dissent, decisions | Committee |
| `portfolio` | portfolios, accounts, cash, positions, snapshots | Portfolio |
| `risk` | policies, assessments, decisions, risk state | Risk |
| `execution` | order intents, paper orders, fills, costs, reconciliation | Execution |
| `research` | datasets, features, strategies, research runs/results | Research |
| `learning` | journal, postmortems, beliefs, calibration | Learning |
| `workflow` | jobs, workflows, outbox, inbox | Orchestration |
| `audit` | audit events, incidents | Audit / Operations |

## Ownership Rule

Only the owning module performs authoritative writes.

Other modules use:

- application interfaces;
- domain events;
- approved read models.

Direct cross-module table writes are prohibited.
