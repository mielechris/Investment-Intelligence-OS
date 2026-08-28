# Batch 9H — Autonomous Market Benchmark + Miss Learning Loop

## Objective
Turn the Batch 9G scorecard into an automatic daily factory-grade by collecting a market benchmark independently of IIOS promotion decisions and comparing IIOS against that benchmark after each regular session.

## Architecture

1. **Independent benchmark collector** — every five minutes during the U.S. regular session, `iios_market_benchmark_collector.py` queries the day-gainers, day-losers, and most-active screeners directly and filters them to the strict governed universe. It does not read or write the IIOS ledger.
2. **Sidecar raw history** — sanitized observations are appended to `~/Library/Application Support/IIOS/market-validation/benchmark_raw/YYYY-MM-DD.jsonl`.
3. **Benchmark builder** — `market_benchmark.py` determines when each ticker first met the independent material-move/volume criteria and builds the daily opportunity truth set. Benchmark completeness requires adequate full-session sampling plus opening and closing coverage.
4. **Read-only IIOS scorecard** — after the close, `iios_daily_market_validation.py` passes that opportunity set into Batch 9G's read-only scorecard.
5. **Miss-learning report** — `market_validation_learning.py` explains misses, detection latency, low promotion conversion, false positives, cadence problems, and provider failures. Recommendations are advisory only.
6. **Private remote copy** — a compact daily report is published to the private `IIOS-Telemetry` repository in the issue `IIOS Market Validation - Latest`.

## Independence contract
The benchmark may share the strict governed universe with IIOS, but it does not import 9E radar/promotion logic and does not use IIOS promotions to define the benchmark opportunity set. Its source is `BATCH_9H_INDEPENDENT_YAHOO_SCREENER_SIDECAR`.

## Opportunity criteria v1
A governed ticker qualifies for the benchmark when the independent collector first observes one of the following:

- absolute daily move >= 3%; or
- absolute daily move >= 2% with volume >= 1.5x average; or
- absolute daily move >= 2% while appearing in at least two independent Yahoo screener categories.

These criteria define the validation benchmark only. They do not create trade signals or alter 9E promotion thresholds.

## Benchmark completeness
A day is `benchmark_complete=true` only when:

- sample coverage is at least 60% of the expected five-minute regular-session samples;
- all three screener families were observed;
- collection includes the opening portion of the session; and
- collection reaches the closing portion of the session.

If completeness fails, the learning engine reports `VALIDATION_INCOMPLETE` and does not treat false-positive conclusions as tuning evidence.

## Learning authority
Batch 9H may recommend review of discovery coverage, radar ranking, evidence filters, provider reliability, or collection cadence. It cannot automatically change numeric thresholds, Committee rules, Risk rules, capital authority, broker settings, or execution permissions.

## Runtime safety
- 9G telemetry remains active and untouched.
- 9H adds two isolated macOS LaunchAgents: `com.iios.market-benchmark` at 300 seconds and `com.iios.market-validation` at 900 seconds.
- The collector has no ledger access.
- The scorecard uses SQLite read-only access.
- No inbound network service is created.
- Broker connected: false.
- Live execution: false.

## First-day behavior
If Batch 9H is activated after the market has already opened, that day's benchmark will likely be incomplete. This is expected and is deliberately surfaced as incomplete rather than backfilled or fabricated. The first full regular session after activation is the first session eligible for a complete benchmark grade.
