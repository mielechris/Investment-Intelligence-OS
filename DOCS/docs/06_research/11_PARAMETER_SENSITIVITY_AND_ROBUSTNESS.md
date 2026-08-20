# Parameter Sensitivity and Robustness

## Principle

A durable edge should not depend on one exact parameter combination.

## Required Tests

- entry threshold perturbation;
- exit threshold perturbation;
- holding-period variation;
- lookback variation;
- position-size variation;
- source-quality threshold variation;
- event-window variation.

## Stability Map

Report a parameter neighborhood, not only the optimum.

## Fragility Warning

Red flags:

- one sharp peak;
- performance collapses with small change;
- one instrument dominates;
- one year dominates;
- one event dominates;
- one regime dominates;
- result depends on one data vendor.

## Bootstrap / Resampling

Where appropriate, estimate uncertainty through resampling.

## Multiple Testing

Record:

- number of parameter sets tried;
- number of strategy variants tried;
- selection process.
