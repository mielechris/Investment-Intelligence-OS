# Batch 9I — Shadow Strategy & Counterfactual Lab

## Objective
Use complete Batch 9H independent market-validation sessions to test alternative IIOS research/promotion configurations without changing the running factory.

## Production Baseline
- deterministic opportunity promotion score floor: 45
- hard evidence: valid current quote plus at least two current news records
- recent governed-case cooldown remains a hard block
- Batch 9E promotion-candidate research breadth: top 8 radar names
- Batch 9E maximum promotions per cycle: 5

## Counterfactuals
### Promotion scenarios
The lab replays persisted Batch 9E promotion-candidate rows using alternative deterministic score floors (40, 45, 50, 55, 60, 65) and shadow case capacities (2, 3, 5). Quote/news requirements and recent-case cooldown are never relaxed.

### Radar breadth analysis
The lab separately measures benchmark recall across the persisted ranked-candidate top 5, 8, 12, 20 and 40. This is a breadth/recall diagnostic only. It does not infer promotion eligibility beyond the persisted top-8 promotion-candidate rows.

## Multi-session governance
A single market day may produce counterfactual results, but threshold advice remains locked until at least five complete Batch 9H benchmark sessions are available. Before five complete sessions the rollup status is `WARMUP_COLLECTING_COMPLETE_SESSIONS` and recommendations remain empty.

When enough sessions exist, the lab may surface a small advisory frontier of shadow scenarios that captured additional benchmark opportunities without exceeding the governed shadow-load/noise limits. Every recommendation is `HUMAN_REVIEW_ONLY`.

## Data flow
1. Batch 9H independently observes the market and builds the end-of-session benchmark.
2. Batch 9I reads the corresponding 9H benchmark/scorecard artifacts.
3. Batch 9I reads persisted Batch 9E radar cycles from `iios_ledger.db` using SQLite read-only mode.
4. The lab replays shadow scenarios and compares them with the current production baseline.
5. Results are written outside the ledger and a compact copy is published to the private `IIOS-Telemetry` repository issue `IIOS Shadow Strategy - Latest`.

## Mac runtime
Batch 9I uses a separate LaunchAgent:
- label: `com.iios.shadow-counterfactual`
- cadence: every 1800 seconds
- automatic work window: after 16:20 New York time

The process self-skips before the shadow window, on non-market days, when no complete Batch 9H sessions exist, or when the latest complete session has already been evaluated.

## Safety invariants
- live ledger access: read-only only
- no ledger mutation functions
- no automatic threshold changes
- no Committee gate changes
- no Risk gate changes
- no capital authority
- no broker connectivity
- no live execution
- Batch 9G telemetry is not restarted or replaced
- Batch 9H benchmark/validation LaunchAgents are not restarted or replaced

## Promotion policy
Batch 9I is a measurement and advisory layer. Any future change to a production threshold requires a separate governed engineering decision, explicit review, its own tests, and a new promotion step. Shadow results never apply themselves.
