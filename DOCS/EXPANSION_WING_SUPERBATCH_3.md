# Expansion Wing Superbatch 3 — Read-Only Schema Integration

## Source contracts

The mappings are derived from source-controlled producers, not operational data. Fixtures are copied and minimized representations of their sanitized output shapes and carry `COPIED_SANITIZED_CONTRACT_FIXTURE_NON_LIVE`.

| Source | Source-controlled contract | Timestamp/freshness | Normalized content |
|---|---|---|---|
| 9A | `iios_observation_runner.py` observation state | `last_cycle_completed_at` | mode, cycle identity, status |
| 9B | `governed_paper_trading_controller.py` state | `cycle_completed_at` | mode, cycle identity, status |
| 9E | `high_speed_market_radar.py` state | `last_cycle_completed_at` | universe, screen, candidate and promotion counts |
| 9H | `market_benchmark.py` / `market_validation_scorecard.py` | `observed_at` | session, completeness, opportunities, detections and misses |
| 9I | `shadow_counterfactual.py` rollup | `generated_at` | maturity, sessions and read-only policies |
| 9J | `outcome_labeling_memory.py` browser summary | `generated_at` | maturity, outcome counts and bounded recent outcomes |
| Paper fund | `paper_portfolio_core.py` read model | `generated_at` | $10K account, cash, NAV, P&L and positions |

Unversioned 9A, 9B, 9E and paper-fund artifacts are explicitly recognized as their source-controlled legacy shape. Unknown versions, missing timestamps and cross-session mismatches become `INCOMPLETE`; absent or malformed files become `UNAVAILABLE`; expired timestamps become `STALE`.

## Bounded compositor

The compositor accepts at most seven JSON artifact paths, each capped at 2 MB by the artifact adapter. It maps and sanitizes every source, calculates freshness against an injectable clock, records content hashes and duplicate/error receipts, and checks that the 9H session is represented in 9I. It does not import the ledger or write a snapshot.

## Strategic Book

Strategic entry now requires a valuation object, thesis and invalidation. The simulator supports marks, cost-modeled partial and full exits, realized P&L, cash restoration, book isolation and whole-fund reconciliation. It remains in-memory and paper-only.

## Frontend provider

One provider owns polling and distributes one immutable snapshot through React context. Room components do not fetch independently. Fixture mode remains the default; Backend 8002 is addressed only when both the live-read-only and recovery-green build gates are explicitly enabled.
