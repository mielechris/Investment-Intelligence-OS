# X3 Canonical Art Direction — IIOS Intelligence Factory

Reference target: the approved black/brass/amber mob-deal-room factory composition supplied by the operator on 2026-08-26.

## Visual hierarchy

1. IIOS Intelligence Factory masthead and operating metrics.
2. Market/factory status surface.
3. Boss / CIO hierarchy panel.
4. Eight specialist portrait bays.
5. Risk Inspection, Paper Execution, Prediction Receipts, Bullshit Detector, Graveyard.
6. Lower operating floor driven by real telemetry.
7. MAX — Chief Bullshit Officer — reacts to real state but never creates or implies state.

## Canonical material language

- Near-black industrial background.
- Brass / antique-gold frames and typography.
- Amber practical lighting rather than generic blue SaaS glow.
- Green reserved for confirmed healthy / active governed state.
- Red reserved for violation, rejection, offline, or explicit challenge states.
- Purple may be used sparingly for the Graveyard / dead-idea archive.
- Dense deal-room composition; avoid modern card-dashboard emptiness.

## Truth rules

- No displayed performance number may be invented to match the reference art.
- No desk may light unless `/agents` state or recent ledger activity supports it.
- No case may move unless `active_room` or accepted canonical ledger translation supports it.
- Unknown remains UNKNOWN. Offline remains OFFLINE.
- Live-capital status must remain explicit.
- Paper/shadow mode must remain explicit.
- Decorative gauges must be labeled as entertainment/non-investment telemetry when not sourced from governed backend data.
- Boss and agent portrait art may be decorative, but cannot claim runtime behavior.
- MAX is a character/reaction surface, never a source of truth.

## Current implementation

`FRONT END/src/SpecialistDeskFloor.tsx` is the first canonical-art implementation. It binds the visual language to:

- `/agents`
- `/factory-room/status`
- `/system/status`
- `activity.recent_events`
- safety invariants
- live-capital lock
- paper mode
- paper portfolio telemetry when available

The safe preview gate remains `python3 scripts/apply_experience_x2.py` on branch `feature/iios-experience-x0-x1`.
