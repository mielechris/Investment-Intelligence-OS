# Research Engine Implementation

## Components

```text
DatasetManifestRegistry
PointInTimeDatasetBuilder
FeatureRegistry
LabelRegistry
BaselineLibrary
EventStudyEngine
BacktestEngine
WalkForwardRunner
SensitivityRunner
RegimePerformanceReporter
```

## Dataset Builder

Every row/object must be eligible at the simulated cutoff.

## Baselines

Implement first:

- cash;
- broad index;
- buy-and-hold;
- simple trend.

## Event Study

Inputs:

- event set;
- event timestamps;
- benchmark;
- pre/post windows;
- exclusions.

Outputs:

- abnormal return distribution;
- hit rate;
- favorable/adverse excursion;
- sample count.

## Backtest

Use:

- strategy version;
- dataset manifest;
- execution cost model;
- risk assumptions.

## Costs

Show gross and net.

## Walk-Forward

Never tune using the final test window.

## Result Storage

Every run persists:

- code commit;
- dataset hash;
- parameters;
- seed;
- dependency lock;
- results;
- warnings.
