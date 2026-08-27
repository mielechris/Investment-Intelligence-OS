# Batch 9C — Paper Fund Operations UI

## Purpose

Turn the existing governed IIOS paper system into a browser-visible operating scoreboard without adding any new decision or execution authority.

## Browser experience

Batch 9C adds a persistent **PAPER FUND OPS** dock on top of the existing Factory Intelligence + X0–X6 shell. The board is open by default and can be minimized.

It shows:

- $10,000 paper NAV, cash, market value, P&L, drawdown, positions and snapshot count.
- Batch 9A Observation cadence, last scan size, research queue count and latest promoted case.
- Batch 9B Paper Trading cadence, inspected cases, latest deepening activity, paper execution window and paper-order count.
- Governed case journey / gate states for the current fund-focus case.
- Latest 9B case classifications: rejected, waiting, capital-path and executed states.
- Current paper positions and recent governed paper orders.
- Permanent safety rail: broker false, live capital locked, live execution false.

## Data source

The browser polls one new read-only endpoint:

`GET /paper-fund/operations`

The feed aggregates existing persisted IIOS objects only:

- governed paper portfolio state and performance history;
- Batch 9A `observation_operations_state`;
- Batch 9B `governed_paper_trading_state`;
- latest Evidence Gap Hunt;
- recent `governed_paper_execution` records.

The selected/focus case journey continues to use the existing read-only Factory Intelligence case endpoint.

## Governance

Batch 9C cannot:

- run a case;
- deepen research;
- prepare a paper authorization;
- submit a paper order;
- mark the portfolio;
- connect a broker;
- change Committee, Risk or Capital authority;
- enable live trading.

The board is observation only. Unknown or missing state remains explicit rather than being synthesized.

## Release gate

`.github/workflows/batch9c-paper-fund-operations.yml` verifies:

- Python compile of the read-only feed;
- static read-only authority contract;
- no live-execution permission in the Batch 9C surface;
- full frontend production build.
