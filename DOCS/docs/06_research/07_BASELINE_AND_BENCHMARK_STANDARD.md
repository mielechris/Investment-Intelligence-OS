# Baseline and Benchmark Standard

Every strategy must face a simple benchmark.

## Required Candidate Baselines

Depending on strategy:

- cash;
- broad index;
- equal-weight universe;
- buy-and-hold;
- simple trend;
- simple mean reversion;
- sector index;
- matched commodity;
- random-entry timing;
- shuffled-event timing;
- previous-value forecast.

## Purpose

Baselines test whether complexity adds value.

## Randomization Tests

Where useful:

- shuffle event dates;
- shuffle signals;
- randomize instrument assignment;
- randomize entry timing.

If performance survives randomization, the strategy may be capturing an unintended exposure.

## Benchmark Change

Changing the benchmark after seeing results requires a new research version.
