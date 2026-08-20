# Operating Model

## 1. Objective

Operate IIOS as a controlled decision system rather than an always-on autonomous trader.

## 2. Core Daily Loop

```text
Check health
→ Ingest
→ Normalize
→ Update world state
→ Build evidence and reasoning
→ Run agents
→ Convene committee
→ Apply risk
→ Paper execute or no-trade
→ Monitor
→ Reconcile
→ Journal
→ Learn
```

## 3. Operator Responsibilities

The owner/operator is responsible for:

- approving material configuration changes;
- reviewing critical incidents;
- approving release promotion;
- reviewing risk-policy changes;
- confirming recovery from stand-down;
- approving any future transition beyond paper mode.

## 4. Automated Responsibilities

Automation may:

- ingest approved sources;
- schedule workflows;
- retry safe jobs;
- build world state;
- run agents;
- create committee sessions;
- compute deterministic risk;
- create paper orders;
- reconcile paper state;
- generate reports.

Automation may not:

- enable live execution;
- override risk veto;
- use quarantined data;
- alter the Constitution;
- deploy unapproved models/prompts;
- erase audit history.

## 5. Operational States

```text
NORMAL
DEGRADED
STAND_DOWN
RECOVERY
MAINTENANCE
```

## 6. Escalation

Any critical integrity issue moves the system toward `STAND_DOWN`.

## 7. Source of Truth

Authoritative operational state exists in PostgreSQL and governed object storage, not the UI, local notes, or model memory.
