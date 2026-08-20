# Backtesting Standard

## Required Inputs

- registered strategy version;
- dataset manifest;
- benchmark;
- cost model;
- risk model;
- execution model;
- start/end dates;
- seed where stochastic.

## Required Outputs

- gross return;
- net return;
- benchmark return;
- benchmark-relative return;
- volatility;
- drawdown;
- recovery time;
- hit rate;
- average win;
- average loss;
- payoff ratio;
- turnover;
- gross exposure;
- net exposure;
- concentration;
- capacity;
- number of trades;
- number of independent events.

## Prohibited Practices

- using future data;
- dropping losing trades without rule;
- changing parameters after reviewing holdout;
- using unrealistic fills;
- ignoring delisted assets;
- ignoring transaction costs;
- comparing against irrelevant benchmark;
- annualizing tiny samples without warning.

## Reproducibility

Backtest result must be reproducible from:

- code commit;
- dependency lock;
- dataset hash;
- strategy version;
- parameters;
- seed;
- cost model.
