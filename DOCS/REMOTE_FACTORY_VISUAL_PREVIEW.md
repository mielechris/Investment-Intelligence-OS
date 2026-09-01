# Remote Factory Visual Preview

This branch is the remote-display counterpart of the accepted Batch 9L V7
cinematic Factory interface.

## Source and safety

- Visual source: `feature/batch9l-v77-voice-audio-soundstage`
- Preview branch: `feature/remote-factory-visual-preview`
- Vercel root directory: `FRONT END`
- The Mac backend at `127.0.0.1:8002` remains unchanged.
- No broker credentials or write-capable secrets are deployed.
- `LIVE_EXECUTION` remains false.
- Telemetry connection is deferred to a sanitized read-only bridge.

This preview is intended to reproduce the local Factory Floor, Control Room,
Factory Watch, MAX, character desks, Family Rules, and Graveyard visual line.
