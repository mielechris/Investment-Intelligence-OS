# Intraday Monitoring Runbook

## Monitor

- critical source freshness;
- market-data freshness;
- scheduled economic events;
- active thesis catalysts;
- invalidation conditions;
- drawdown;
- concentration;
- model failures;
- job backlog;
- paper execution state.

## Event Reaction

For a material event:

1. ingest and validate source;
2. update world state;
3. determine affected theses;
4. rerun required agents;
5. reconvene committee if material;
6. refresh risk;
7. create paper action only with valid risk approval.

## Prohibited Shortcut

Do not manually create a paper order because a headline “looks obvious.”

## Intraday Stand-Down Triggers

- stale critical market data;
- risk engine unavailable;
- accounting mismatch;
- duplicate execution behavior;
- security incident;
- unexpected environment state.
