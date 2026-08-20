# Implementation Master Plan

## Phase 0 — Repository Confirmation

Before coding:

- Packages 01–10 are in `docs/`;
- Git repository is clean;
- current branch is known;
- GitHub Desktop shows no uncommitted documentation changes;
- local machine has development prerequisites;
- PAPER mode remains the only execution environment.

## Phase 1 — Platform Skeleton

Implement:

- repository root files;
- Python backend package;
- TypeScript frontend;
- configuration;
- PostgreSQL;
- object storage;
- migrations;
- structured logs;
- health endpoint;
- durable jobs.

Success:

```text
frontend starts
api starts
worker starts
scheduler starts
postgres is healthy
object store is healthy
/health is healthy
```

## Phase 2 — Data Pipeline

Implement:

- source registry;
- rights;
- raw object storage;
- retrieval;
- parser registry;
- normalizer registry;
- deduplication;
- revisions;
- health;
- quarantine.

Success:

```text
approved source
→ raw payload
→ canonical event
```

## Phase 3 — Knowledge and Reasoning

Implement:

- entities;
- resolution;
- relationships;
- world-state snapshot;
- evidence;
- claims;
- causal chain;
- counter-chain;
- hypothesis;
- thesis;
- explainability packet.

## Phase 4 — AI Team

Implement:

- model gateway;
- model registry;
- prompt registry;
- governed retrieval;
- agent executor;
- Policy Analyst;
- Macro Analyst;
- Skeptic;
- committee.

## Phase 5 — Risk and Paper Execution

Implement:

- paper account;
- portfolio snapshot;
- risk policy;
- risk assessment;
- risk decision;
- order intent;
- paper order;
- fill;
- accounting;
- reconciliation;
- kill switch.

## Phase 6 — Research

Implement:

- dataset manifests;
- point-in-time dataset builder;
- baselines;
- event studies;
- backtests;
- walk-forward;
- postmortems;
- calibration.

## Phase 7 — Command Center

Implement:

- API queries;
- Today page;
- Event Radar;
- World State;
- Committee;
- Risk;
- Portfolio;
- Journal;
- Research;
- System Health.

## Phase 8 — Hardening

Implement:

- CI;
- architecture tests;
- constitutional tests;
- golden trace;
- backups;
- restore;
- release manifest;
- release checklist.

## Implementation Priority

If schedule becomes tight:

1. correctness;
2. point-in-time integrity;
3. risk;
4. audit;
5. working vertical slice;
6. user experience;
7. breadth;
8. optimization.

Do not sacrifice the first four to gain the last four.
