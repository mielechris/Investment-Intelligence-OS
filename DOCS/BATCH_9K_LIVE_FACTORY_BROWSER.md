# Batch 9K — Live Factory Browser Preview

## Objective

Expose the running IIOS market-validation stack in a browser without restarting or modifying Backend 8002 or any Batch 9G–9J worker.

## Preview architecture

`http://127.0.0.1:5176` serves a built React preview and a localhost-only `/validation/stack` endpoint.

The page combines:

- existing `FactoryIntelligenceUI` which continues to read the running Backend 8002;
- Batch 9E/9G opportunity and telemetry state from the sanitized local telemetry snapshot;
- Batch 9H independent market validation from its local sidecar output;
- Batch 9I shadow strategy results from its local sidecar output;
- Batch 9J outcome learning memory from its browser-ready local JSON.

The 9K validation bridge does not import the IIOS ledger, SQLite, GitHub CLI, broker code, Committee/Risk code, or execution code.

## Browser semantics

Missing data is displayed as WAITING. Old high-frequency telemetry is displayed as STALE. No placeholder market metrics are invented.

The top market-operations view shows:

- governed universe size;
- 9E screener hits;
- Grok and Gemini candidate counts;
- promotion queue size;
- 9A/9B/9E cadence;
- paper NAV and position count;
- 9H benchmark/detection/miss metrics when available;
- 9I warm-up and recommendation state;
- 9J outcome-labeling, five-day maturity and review-queue state;
- agent outcome-alignment scorecards when mature data exists.

## Activation safety

The activation script:

1. leaves the live IIOS checkout on its current branch;
2. creates/refreshes a detached Batch 9K worktree;
3. runs `npm ci`, lint and production build in that worktree;
4. verifies the existing Backend 8002 read-only Factory Intelligence contract is reachable;
5. fingerprints the existing 9G, 9H, 9I and 9J LaunchAgent plist files;
6. installs only `com.iios.factory-browser-preview`;
7. verifies `/health` and `/validation/stack` on localhost;
8. rechecks the protected LaunchAgent fingerprints and live checkout state;
9. opens `http://127.0.0.1:5176`.

## Authority boundary

- validation bridge ledger access: NONE
- Backend 8002: unchanged
- 9G/9H/9I/9J LaunchAgents: unchanged
- threshold-change authority: FALSE
- Committee override: FALSE
- Risk override: FALSE
- capital authority: FALSE
- broker connectivity: FALSE
- live execution: FALSE

## Next step after preview acceptance

Once the preview is visually accepted against live factory behavior, promote the validated browser composition into the normal IIOS browser route. That production UI promotion should be a packaging/routing change only; the 9E–9J intelligence stack remains the same.
