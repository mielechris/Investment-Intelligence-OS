# Execution Cost and Capacity Model

## Cost Components

Research must model:

- bid/ask spread;
- commissions;
- exchange or platform fees;
- slippage;
- market impact approximation;
- borrow cost where relevant;
- futures roll;
- option spread and decay where relevant;
- funding costs where relevant;
- turnover.

## Liquidity

Estimate:

- average daily volume;
- quoted spread;
- depth where available;
- participation rate;
- gap risk.

## Capacity

Capacity asks:

> How much capital can this strategy reasonably deploy before its own execution degrades the edge?

## Cost Sensitivity

Every promoted strategy must report results under:

- base costs;
- 1.5× costs;
- 2× costs.

A strategy that disappears under small cost changes is fragile.

## Paper Fill Model

Paper validation should use conservative assumptions rather than idealized fills.
