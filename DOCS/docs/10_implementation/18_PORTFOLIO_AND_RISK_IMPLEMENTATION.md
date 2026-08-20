# Portfolio and Risk Implementation

## Paper Portfolio

Create:

```text
Portfolio
PaperAccount
CashLedger
Position
PositionLot
PortfolioSnapshot
ExposureSnapshot
```

## Initial Risk Policy

Store policy in database/config, not only constants.

Initial values may use the V1 governance defaults.

## Exposure Calculation

Calculate:

- single instrument;
- sector;
- asset class;
- country;
- currency;
- commodity;
- policy theme;
- causal cluster;
- strategy.

## Risk Assessment

Input:

- thesis;
- committee decision;
- portfolio snapshot;
- current prices;
- liquidity;
- volatility;
- correlation;
- data health;
- risk policy.

## Rule Execution

Deterministic rules return:

```text
PASS
REDUCE
VETO
```

## Risk Decision

Persist:

- triggered rules;
- max quantity;
- max notional;
- reasons;
- expiry.

## Kill Switch

Durable system state.

When active:

```text
reject new order intents
allow diagnostics
allow reconciliation
```

## Tests

- high-confidence oversized position still vetoed;
- three stocks sharing one policy theme hit cluster cap;
- stale critical price feed blocks risk;
- accounting mismatch blocks risk.
