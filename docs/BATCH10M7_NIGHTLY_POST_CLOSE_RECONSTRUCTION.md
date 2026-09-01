# Batch 10M.7 — Nightly Post-Close Reconstruction

Batch 10M.7 turns the existing governed historical stack into a repeatable nightly learning cycle without adding trading authority.

## What it does

After the U.S. market session, the worker:

1. waits until **16:20 America/New_York** on a weekday;
2. runs one complete Batch 10J historical event-reconstruction pass across the eight-symbol rotation (`SPY`, `QQQ`, `AAPL`, `MSFT`, `NVDA`, `TSLA`, `AMZN`, `META`);
3. refreshes Batch 10K historical macro/regime normalization using the same historical-research library;
4. writes a combined nightly provenance artifact;
5. marks that ET market date complete so the same date is not reconstructed twice.

This is historical research and learning infrastructure. It is **not** a current-market trading engine, a buy signal, or a replacement for 9H independent validation.

## Runtime isolation

The scheduler wakes every 15 minutes, but the worker itself enforces the 16:20 ET weekday guard and once-per-market-date idempotency.

The macOS activation path uses a Terminal Bridge:

- runtime root: `~/.iios/nightly-reconstruction`
- launchd label: `com.iios.nightly-reconstruction`
- launchd opens a `.command` in Terminal rather than directly executing repository Python from `~/Documents/GitHub`
- 9A Observation: unchanged
- 9B Paper Trading: unchanged
- 9E Radar: unchanged
- Backend 8002: unchanged

## Artifacts

Default IIOS application-data root:

`~/Library/Application Support/IIOS`

10M.7 writes:

- `nightly-reconstruction/latest_nightly_reconstruction.json`
- `nightly-reconstruction/nightly_reconstruction_<YYYY-MM-DD>.json`
- `nightly-reconstruction/nightly_reconstruction_state.json`

It reuses existing 10J and 10K artifact directories:

- `historical-event-reconstruction/`
- `historical-macro-regime/`
- historical source library: `historical-research/`

## Safety contract

Every 10M.7 report keeps these invariants explicit:

- advisory only
- paper-mode only
- live execution false
- live capital locked
- trade execution permission false
- no broker authority
- no Committee or Risk authority
- no automatic parameter changes
- no case-promotion authority

An engine failure produces an `ERROR` report and **does not** advance the completed market date, so a later scheduled cycle can retry safely.

## Commands

Run one governed cycle manually after the guard is open:

```bash
/usr/bin/python3 scripts/iios_nightly_post_close_reconstruction.py --run-once
```

Read worker state without mutation:

```bash
/usr/bin/python3 scripts/iios_nightly_post_close_reconstruction.py --status
```

Install the isolated Terminal-Bridge scheduler:

```bash
/usr/bin/python3 scripts/activate_batch10m7_nightly_post_close_reconstruction.py --activate
```

Inspect scheduler state:

```bash
/usr/bin/python3 scripts/activate_batch10m7_nightly_post_close_reconstruction.py --status
```

Deactivate only this worker:

```bash
/usr/bin/python3 scripts/activate_batch10m7_nightly_post_close_reconstruction.py --deactivate
```

`--force` exists only for controlled historical backfill/acceptance work. It bypasses the time/idempotency guard but does not change any safety or execution authority.

## Acceptance gate

10M.7 is code-complete when CI proves:

- new worker compiles;
- pre-close and weekend guards block engine calls;
- post-close runs 10J before 10K;
- the 10J pass requests eight symbols;
- once-per-date idempotency works;
- failures remain retryable and fail closed;
- safety authority remains false/locked;
- Terminal-Bridge runtime is outside `~/Documents/GitHub`;
- inherited 10J and 10K contracts continue to pass.

Runtime acceptance is separate from CI: keep the PR draft until the macOS worker is installed and its first real post-close artifact is verified.
