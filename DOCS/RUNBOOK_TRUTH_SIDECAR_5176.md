# Truth Sidecar (Port 5176) Operations Runbook

Read-only IIOS-9L-V7-LIVING factory truth sidecar. Serves the built frontend
(`FRONT END/dist`) and the read-only `/health`, `/living/overview`, and
`/truth/factory` endpoints on `127.0.0.1:5176`. It never writes to the
ledger, never talks to a broker, and never enables live execution or trade
authority.

launchd label: `com.iios.v7living-truth-sidecar`
Installed plist: `~/Library/LaunchAgents/com.iios.v7living-truth-sidecar.plist`
Repository template: `ops/launchd/com.iios.v7living-truth-sidecar.plist`

**Retired (Phase 5):** a pre-existing, unrelated
`com.iios.factory-browser-preview.plist` also targeted port 5176 but pointed
at a different, stale checkout
(`Investment-Intelligence-OS-batch10l-10m-measurement-health-superbatch`)
with no `--ledger-path`. It was never loaded at the time of retirement, but
its presence in `~/Library/LaunchAgents/` meant macOS could auto-load it at
a future login and reintroduce a wrong-checkout sidecar on 5176. It has been
moved out of `~/Library/LaunchAgents/` into a disabled-services archive so it
can no longer auto-load. See "Retired stale service archive" below for the
exact archive path, checksum, and restoration command.

## Retired stale service archive (Phase 5)

- **Old label:** `com.iios.factory-browser-preview`
- **Old config:** `RunAtLoad: true`, `KeepAlive: true`, port `5176`,
  `ProgramArguments` running
  `/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch10l-10m-measurement-health-superbatch/scripts/iios_factory_browser_preview.py`
  with `--root .../FRONT END/dist --host 127.0.0.1 --port 5176` (no
  `--ledger-path`), `WorkingDirectory` set to that same stale checkout.
- **Reason retired:** wrong checkout, no explicit ledger path, latent risk of
  auto-loading at login and colliding with the correct
  `com.iios.v7living-truth-sidecar` service on port 5176.
- **Load state at retirement:** not loaded (`launchctl print` returned "could
  not find service"; confirmed via `launchctl list` as well).
- **Archived copy:** `~/Library/Application Support/IIOS/DisabledLaunchAgents/com.iios.factory-browser-preview.plist.disabled-20260902T054606Z`
- **SHA-256 checksum:** `58b6cb05367ad128d6c0ad93da4c724120a4ac27ff0538741b6e7f6ab71d6296`
  (verified identical between the original and the archived copy before the
  original was removed from `~/Library/LaunchAgents/`)
- **Original logs (preserved in place, untouched):**
  - `~/Library/Logs/IIOS/factory-browser-preview.out.log` (2,265,189 bytes as of retirement)
  - `~/Library/Logs/IIOS/factory-browser-preview.err.log` (6,318,118 bytes as of retirement)

### Restoration procedure (only if the stale checkout must be revived)

```zsh
cp "$HOME/Library/Application Support/IIOS/DisabledLaunchAgents/com.iios.factory-browser-preview.plist.disabled-20260902T054606Z" \
   "$HOME/Library/LaunchAgents/com.iios.factory-browser-preview.plist"
shasum -a 256 "$HOME/Library/LaunchAgents/com.iios.factory-browser-preview.plist"
# Expect: 58b6cb05367ad128d6c0ad93da4c724120a4ac27ff0538741b6e7f6ab71d6296
plutil -lint "$HOME/Library/LaunchAgents/com.iios.factory-browser-preview.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.iios.factory-browser-preview.plist"
```

Restoring this service will make it compete for port 5176 with
`com.iios.v7living-truth-sidecar`; do not restore it while the correct
service is running unless you first change one of their ports.

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
