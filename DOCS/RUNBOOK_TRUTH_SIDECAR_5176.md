# Truth Sidecar (Port 5176) Operations Runbook

Read-only IIOS-9L-V7-LIVING factory truth sidecar. Serves the built frontend
(`FRONT END/dist`) and the read-only `/health`, `/living/overview`, and
`/truth/factory` endpoints on `127.0.0.1:5176`. It never writes to the
ledger, never talks to a broker, and never enables live execution or trade
authority.

launchd label: `com.iios.v7living-truth-sidecar`
Installed plist: `~/Library/LaunchAgents/com.iios.v7living-truth-sidecar.plist`
Repository template: `ops/launchd/com.iios.v7living-truth-sidecar.plist`

**Important:** a pre-existing, unrelated
`~/Library/LaunchAgents/com.iios.factory-browser-preview.plist` also targets
port 5176 but points at a different, stale checkout
(`Investment-Intelligence-OS-batch10l-10m-measurement-health-superbatch`)
and has no `--ledger-path`. It is currently unloaded. Do **not** load it — if
it were ever loaded it would occupy port 5176 with the wrong checkout. None
of the scripts here touch that file.

## Install

```zsh
cd "/Users/crm/Documents/GitHub/IIOS-9L-V7-LIVING"
scripts/ops/install_truth_sidecar_5176.sh
```

This validates the plist (`plutil -lint`), confirms `FRONT END/dist/index.html`
exists, copies the plist into `~/Library/LaunchAgents/`, boots out any prior
instance of this exact label only, bootstraps it into the user's `gui`
domain, enables it, and kickstarts it.

## Status

```zsh
launchctl print gui/$(id -u)/com.iios.v7living-truth-sidecar
```

Look for `state = running` and the `pid` line.

## Health verification

```zsh
scripts/ops/verify_truth_sidecar_5176.sh
```

Checks: launchd load state, that port 5176 is bound to `127.0.0.1` only,
`/health`, `/living/overview` reachability, and `/truth/factory` identity
(checkout, ledger path, invariants, $10,000 cash-only paper account, zero
positions). Exits non-zero if any check fails.

Manual spot checks:

```zsh
curl -s http://127.0.0.1:5176/health
curl -s http://127.0.0.1:5176/living/overview
curl -s http://127.0.0.1:5176/truth/factory
```

## Restart

Deliberate restart (does not touch backend 8002 or 9A/9B/9E):

```zsh
launchctl kickstart -k gui/$(id -u)/com.iios.v7living-truth-sidecar
```

Simulate a crash to confirm auto-restart:

```zsh
launchctl kill TERM gui/$(id -u)/com.iios.v7living-truth-sidecar
sleep 2
launchctl print gui/$(id -u)/com.iios.v7living-truth-sidecar | grep -E "pid|state"
```

## Logs

```zsh
tail -f ~/Library/Logs/IIOS/v7living-truth-sidecar.out.log
tail -f ~/Library/Logs/IIOS/v7living-truth-sidecar.err.log
```

## Uninstall

```zsh
scripts/ops/uninstall_truth_sidecar_5176.sh
```

Boots out the service and removes the installed plist from
`~/Library/LaunchAgents/`. Does not delete logs, the ledger, or repository
files.

## Manual recovery (without launchd)

If the persistent service must be bypassed temporarily:

```zsh
launchctl bootout gui/$(id -u)/com.iios.v7living-truth-sidecar 2>/dev/null || true
cd "/Users/crm/Documents/GitHub/IIOS-9L-V7-LIVING"
nohup python3 scripts/iios_factory_browser_preview.py \
  --root "FRONT END/dist" --host 127.0.0.1 --port 5176 \
  --ledger-path "BACK END/backend/iios_ledger.db" \
  > /tmp/manual_5176.log 2>&1 &
disown
```

Reinstall the persistent service afterward with
`scripts/ops/install_truth_sidecar_5176.sh`.

## Rollback ports

- `5177`: isolated rollback sidecar, same script/repo, started manually
  (not launchd-managed). Recreate with the same command as above using
  `--port 5177`.
- `5187`: rollback frontend (Vite dev server), started separately via the
  existing `FRONT END` dev workflow (`npm run dev` in that directory), not
  managed by this runbook.

## Safety boundaries

- Never modify, load, or bootout `com.iios.backend8002`,
  `com.iios.batch9a-observation`, `com.iios.batch9b-paper-trading`,
  `com.iios.batch9e-radar`, `com.iios.batch9e-radar-bridge-supervisor`, or
  any other existing `com.iios.*` label.
- Never touch `IIOS-unified-command-center` or `IIOS-remote-observer`.
- The sidecar only performs read-only GETs against the ledger and backend
  8002; it has no ledger write path and no broker/trade-execution code path.
