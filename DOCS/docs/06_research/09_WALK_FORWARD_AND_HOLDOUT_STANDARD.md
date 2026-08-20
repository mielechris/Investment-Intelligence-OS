# Walk-Forward and Holdout Standard

## Holdout

A final holdout must remain untouched during development.

If inspected repeatedly, it becomes validation data.

## Walk-Forward

Preferred workflow:

```text
Train / Develop
→ Test on next window
→ Advance time
→ Refit or recalibrate using only past data
→ Test again
```

## Required Reporting

For each window:

- dates;
- strategy parameters;
- train sample;
- test sample;
- return;
- drawdown;
- turnover;
- calibration;
- regime;
- cost assumptions.

## Stability

The strategy should not depend on one exceptional window.

## Cross-Sectional Validation

Where possible, validate across:

- sectors;
- instruments;
- countries;
- commodities;
- event categories.

## Promotion Rule

Out-of-sample weakness is more important than in-sample strength.
