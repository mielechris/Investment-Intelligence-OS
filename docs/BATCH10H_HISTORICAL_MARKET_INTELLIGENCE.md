# Batch 10H — Historical Market Intelligence & Analog Engine

## Objective

Run a governed historical-research floor continuously, including nights, weekends and holidays. The engine rotates through core market anchors plus current IIOS opportunities and paper positions, refreshes the deepest trustworthy provider history available, measures the actual start/end coverage, constructs comparable prior market setups, and reports forward outcomes at 1/5/20/60 trading-day horizons.

## Truthfulness contract

- Historical coverage is never assumed to begin with the origin of the NYSE or any other market.
- Every dataset reports its actual provider start date, end date, row count and coverage quality.
- Provider failure produces `HISTORICAL_RESEARCH_DEGRADED`; it never creates synthetic market history.
- Current analog features use only information available at each historical date. Forward returns are used only as later outcomes, preventing future leakage into the matching features.
- Price/volatility analogs may be active while historical macro and event/news reconstruction remain explicit measurement gaps.

## 24/7 runtime

The macOS activation installs `com.iios.historical-market-intelligence` at a 15-minute cadence. Each cycle processes a rotating subset of the research queue. Provider downloads are locally cached for six hours, allowing off-hours cycles to continue analysis without repeatedly downloading the same source data. The unified browser publisher refreshes every five minutes and the UI polls the published artifact every 30 seconds.

## Research conveyor

`ARCHIVE SEARCH → ANALOG MATCHING → REGIME NORMALIZATION → EVENT RECONSTRUCTION → FORWARD RETURN STUDY → AGENT MEMORY → JUDGMENT BANK`

The first release fully implements archive price-history search, analog matching, coverage accounting and forward-return studies. Historical macro-regime joins and event/news reconstruction remain labeled partial/gap until governed historical inputs are connected.

## Safety

10H is read-only research. It cannot create orders, manufacture qualification trades, alter thresholds or agent weights, change portfolio exposure, connect a broker, fund an account, authorize capital, or enable live execution. Any future proposal to use historical analog evidence in production routing or weighting must pass measurement, shadow testing and explicit human approval.
