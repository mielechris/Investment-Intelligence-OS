# Stand-Down and Kill-Switch Runbook

## Stand-Down Purpose

Stop creation of new risk while preserving system state and diagnostic capability.

## Automatic Triggers

May include:

- critical source stale;
- critical market data stale;
- risk engine unavailable;
- accounting mismatch;
- duplicate orders/fills;
- portfolio drawdown threshold;
- security incident;
- environment mismatch;
- corrupted state.

## Activation

1. set system state to STAND_DOWN;
2. reject new risk assessments or order intents according to policy;
3. cancel queued nonessential decision workflows;
4. preserve reconciliation and audit;
5. notify operator;
6. create incident if material.

## Kill Switch

Kill switch is stronger than stand-down and may:

- block all new order activity;
- cancel eligible open paper orders;
- force risk review of open positions.

## Recovery

Resume only when:

- root cause identified;
- integrity verified;
- accounting reconciled;
- affected services healthy;
- operator explicitly resumes;
- recovery audit recorded.
