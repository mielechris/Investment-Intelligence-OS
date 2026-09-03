# Expansion Wing persistent preview

Status: implementation-ready, not installed. Label `com.iios.expansion-wing-preview`; loopback `127.0.0.1:5177` only.

## Topology and command

One Python process serves the compiled frontend, `GET /snapshot`, `GET /health`, and `HEAD` equivalents. It composes at most once per 15 seconds; the browser has one 15-second polling owner. Other methods return 405. Static paths are resolved beneath the reviewed build root and responses are capped at 2 MB.

The installed command is generated without personal paths:

```text
<python3> -m expansion_wing.preview_server --port 5177 --static-root <state>/www --state-dir <state> --telemetry <home>/Library/Application Support/IIOS/telemetry/latest.json --validation <home>/Library/Application Support/IIOS/market-validation/latest_market_validation.json --shadow <home>/Library/Application Support/IIOS/market-validation/browser/shadow_strategy.json --outcome <home>/Library/Application Support/IIOS/market-validation/browser/outcome_learning.json --backend http://127.0.0.1:8002/system/status
```

Expected steady state: one Python process, one listener, a small static build, one lock file, one snapshot composition per active browser per cache window at most, and one bounded Backend GET per composition. No database, ledger, provider, credential, scheduler, or broker access exists.

## Installation mutations

`scripts/install_expansion_wing_preview.sh <reviewed-worktree>` validates branch cleanliness, label and port availability, builds with the explicit Expansion Wing live gates, then creates:

- `~/Library/Application Support/IIOS/ExpansionWingPreview/` (0700), including `www/` and `preview.lock`;
- `~/Library/Logs/IIOS/expansion-wing-preview.log`;
- `~/Library/LaunchAgents/com.iios.expansion-wing-preview.plist` (0600);
- one job in `gui/<uid>`.

It does not install packages or modify existing jobs. Installation needs a separate authorization.

## Rollback

Run `scripts/uninstall_expansion_wing_preview.sh`. It boots out only the exact label, removes only its exact plist and state directory, and retains the log for audit. The source branch and all operational services remain unchanged. If startup fails, the service remains unavailable; it never falls back to Backend data or private 9I evidence.

## Health

`/health` contains only service status, schema, aggregate snapshot truth, generated time, source availability categories, Backend reachability category, and fixed false authority fields. Missing safe 9I remains `UNAVAILABLE / BROWSER_SUMMARY_NOT_AVAILABLE`.
