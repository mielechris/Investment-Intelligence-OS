# IIOS Worker Supervision Hardening

## Objective

Remove Batch 9A Observation and Batch 9B Governed Paper Trading from terminal ownership and place them under macOS `launchd` supervision without changing their governed investment logic, paper-only safety model, cadence, broker state, or live-capital authority.

This hardening exists because a restored/closed VS Code terminal can leave a worker no longer running while the ledger continues to show an overdue cadence. The worker code itself remains unchanged.

## Scope

Managed:

- Batch 9A Observation — 15-minute operating cadence.
- Batch 9B Governed Paper Trading — 15-minute operating cadence.
- A read-mostly stale-heartbeat watchdog that may restart only the two managed LaunchAgents.

Explicitly excluded:

- Batch 9E High-Speed Radar.
- Backend 8002.
- Frontend/browser previews.
- Broker connectivity.
- Any live-money authority.
- Committee, Risk, Capital, sizing, authorization, or execution overrides.

## Runtime model

### Layer 1 — launchd KeepAlive

Two LaunchAgents own the existing launchers:

- `com.iios.batch9a-observation`
- `com.iios.batch9b-paper-trading`

The LaunchAgents use `RunAtLoad=true`, `KeepAlive=true`, a 30-second restart throttle, and `AbandonProcessGroup=false`. Closing VS Code or restoring terminal history no longer determines whether the workers remain alive.

### Layer 2 — stale-heartbeat watchdog

`com.iios.worker-watchdog` runs every 300 seconds. It reads the governed SQLite ledger using read-only SQLite mode and checks:

- 9A: `observation_operations_state.last_cycle_completed_at`
- 9B: `governed_paper_trading_state.cycle_completed_at`

A worker becomes recovery-eligible only when its last completed checkpoint is more than 45 minutes old. Activation provides a 60-minute startup grace. After any recovery attempt, that worker receives a 60-minute cooldown before another automatic restart may be attempted.

When recovery is required, the watchdog calls:

`launchctl kickstart -k gui/<uid>/<worker-label>`

This restarts the LaunchAgent job rather than constructing or submitting any investment action.

## Audit trail

The watchdog attempts to persist governed operational audit events:

- `WORKER_AUTO_RECOVERY_REQUESTED`
- `WORKER_AUTO_RECOVERY_KICKSTARTED`
- `WORKER_AUTO_RECOVERY_FAILED`

If audit-event persistence is temporarily unavailable, the watchdog still writes its local append-only operational log under `~/.iios/worker-supervision/watchdog.log`.

## Safety invariants

Worker supervision never changes the following:

- `paper_mode=true`
- broker connected: false
- live execution: false
- live trade execution permission: false
- no Committee override
- no Risk override
- no Capital override
- no sizing override
- no authorization bypass

The installer and watchdog do not import broker SDKs and do not contain an order-submission path.

## Installation / transition

The installer is intentionally non-destructive by default. Running it with no arguments prints and validates the plan only.

Activation is explicit:

```bash
/usr/bin/python3 scripts/install_iios_worker_supervision.py --activate
```

During activation the installer:

1. validates the governed ledger, 9A launcher, 9B launcher, and watchdog paths;
2. unloads any previous versions of these three LaunchAgents;
3. terminates only processes matching the configured 9A and 9B runner fragments so terminal-owned copies cannot duplicate the managed services;
4. writes LaunchAgent plists under `~/Library/LaunchAgents`;
5. writes a 60-minute activation grace checkpoint under `~/.iios/worker-supervision/state.json`;
6. bootstraps and kickstarts 9A and 9B under `launchd`;
7. bootstraps the 5-minute watchdog;
8. leaves 9E untouched.

## Verification

Run:

```bash
/usr/bin/python3 scripts/install_iios_worker_supervision.py --status
```

Expected service state:

- `com.iios.batch9a-observation: LOADED`
- `com.iios.batch9b-paper-trading: LOADED`
- `com.iios.worker-watchdog: LOADED`

Then verify through Batch 9G telemetry that 9A and 9B both return to `ON_CADENCE` after their first managed cycles. The private telemetry sink remains the authoritative remote verification source.

## Logs

LaunchAgent logs are preserved under `~/.iios/logs`:

- `9a.launchd.out.log`
- `9a.launchd.err.log`
- `9b.launchd.out.log`
- `9b.launchd.err.log`
- `worker-watchdog.launchd.out.log`
- `worker-watchdog.launchd.err.log`

Watchdog state and audit fallback logs are preserved under `~/.iios/worker-supervision`.

## Rollback

```bash
/usr/bin/python3 scripts/install_iios_worker_supervision.py --uninstall
```

Uninstall removes the three LaunchAgents but preserves audit state/log files. It does not silently return 9A/9B to terminal ownership; manual workers should only be restarted deliberately after rollback.

## Acceptance criteria

1. Contract test passes.
2. Default installer plan validates without runtime mutation.
3. Activation transitions current terminal-owned 9A/9B processes into LaunchAgents.
4. 9E stays running and unchanged.
5. 9A and 9B each write a fresh governed cycle after activation.
6. Batch 9G telemetry reports 9A/9B/9E `ON_CADENCE` and factory health `HEALTHY`.
7. Closing/reloading VS Code does not stop 9A or 9B.
8. A deliberately stopped managed worker is restarted by `launchd`.
9. A deliberately stale checkpoint is recovered by the watchdog no more frequently than the configured cooldown.
10. Paper fund, broker state, and live-execution safety invariants remain unchanged.
