# Preview Living Wall Publisher

## Scope

This publisher sends sanitized, read-only factory truth from the canonical local
observer at `http://127.0.0.1:5176/living/overview` to the protected Preview
branch alias:

`https://investment-intelligence-os-git-feature-iios-l-104899-chris-2274.vercel.app`

It is restricted to `feature/iios-living-wall-gallery`, `/telemetry/ingest`, and
`/living-wall/truth`. It cannot deploy, rotate credentials, access a ledger,
connect to a broker, alter authority, or target Production.

## Security boundaries

- Local truth must be at most 30 seconds old and no more than five seconds in
  the future.
- `live_execution` must be `false` and `telemetry_read_only` must be `true`.
- Credential-shaped keys are removed recursively before publication.
- The stable Preview hostname and two paths are compiled into the runner and
  independently checked against the source-controlled policy.
- Redirects and retries are disabled. Connect timeout is five seconds and each
  remote request is bounded to fifteen seconds.
- The ingest and Vercel bypass secrets are read from macOS Keychain. They are
  passed to curl through an anonymous pipe, never through argv or environment.
- Logs and status contain only timestamps, event codes, HTTP status, freshness,
  age, and backoff state.
- A nonblocking `fcntl` lock permits at most one publisher cycle at a time.

The local copies of both credentials live only in Keychain. The ingest verifier
also necessarily exists as a sensitive Vercel Preview variable scoped to the
feature branch, and the automation bypass necessarily exists in Vercel project
protection configuration. Vercel automation bypass secrets are project-scoped;
the exact-host/path checks are therefore mandatory local controls.

## Keychain records

| Purpose | Service | Account |
| --- | --- | --- |
| Ingest | `com.iios.living-wall-preview.ingest` | `feature/iios-living-wall-gallery` |
| Bypass | `com.iios.living-wall-preview.vercel-bypass` | `investment-intelligence-os` |

Never use `security add-generic-password -w SECRET`; that exposes a credential
in process arguments. Use an invisible Keychain prompt or an approved native
Security-framework installer. Never use `-A`.

## Controlled installation

Installation is intentionally not automatic:

1. Confirm the feature branch and validated commit are deployed to Preview and
   the stable branch alias points to that READY deployment.
2. Generate a dedicated random ingest token without printing it.
3. Store its local copy in the ingest Keychain record.
4. Add the matching server copy as a sensitive Vercel Preview variable scoped
   only to `feature/iios-living-wall-gallery`.
5. Create a dedicated named Protection Bypass for Automation secret and store
   its local copy in the bypass Keychain record. Do not put it in a URL.
6. Redeploy only the feature Preview so the ingest token becomes active.
7. Run one controlled cycle and require HTTP 202 plus `accepted=true`, followed
   by HTTP 200 `living_wall_truth.v1` with `AVAILABLE/CURRENT` truth and all
   authority disabled.
8. Install the LaunchAgent:

   ```sh
   python3 scripts/install_preview_living_wall_publisher.py --install
   ```

9. Observe at least three 30-second cycles and confirm CURRENT truth.

The generated file is
`~/Library/LaunchAgents/com.iios.living-wall-preview-publisher.plist`. No other
LaunchAgent is read, unloaded, rewritten, or restarted by the installer.

## Health and operation

```sh
python3 scripts/install_preview_living_wall_publisher.py --status
python3 scripts/install_preview_living_wall_publisher.py --stop
python3 scripts/install_preview_living_wall_publisher.py --install
python3 scripts/install_preview_living_wall_publisher.py --uninstall
```

State is stored at
`~/Library/Application Support/IIOS/LivingWallPublisher/status.json`; sanitized
logs are stored at `~/Library/Logs/IIOS/living-wall-preview-publisher.log`.
Failures back off for 30, 60, 120, and then at most 300 seconds. The system
prefers visibly STALE or UNAVAILABLE truth over publishing unsafe data.

## Authenticated browser verification

Open the stable branch alias in an authenticated Vercel browser session. Do not
put the bypass secret in the URL. Verify Gallery, Story, Replay, Command,
Expansion Wing, and Command → Factory Watch. Require `/living-wall/truth` HTTP
200, no Vercel login redirect, no `DATA DEGRADED`, no console/network errors,
and `LIVE EXECUTION: FALSE` throughout.

## Rollback

1. Run `--stop`, then `--uninstall`.
2. Confirm the publisher label is not loaded and no lock holder remains.
3. Remove only the two publisher Keychain records.
4. Remove only the feature-branch Preview ingest variable.
5. Revoke only the dedicated Living Wall bypass secret.
6. Redeploy the validated repair using the untouched general Preview
   configuration if the environment change requires it.
7. Confirm the stable alias remains protected and truth becomes STALE, then
   UNAVAILABLE without republishing.

Sanitized logs are preserved for audit unless their deletion is separately
authorized. Production, aliases, domains, existing IIOS LaunchAgents, workers,
services, ledgers, and authority settings remain untouched.
