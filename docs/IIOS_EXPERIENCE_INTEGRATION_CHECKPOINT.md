# IIOS X0–X6 Experience Integration Checkpoint

Date: 2026-08-26

## Integration branch

- Branch: `integration/iios-experience-x0-x6`
- Base engineering branch: `feature/batch8-paper-portfolio`
- Base engineering commit at branch creation: `db379c7dddbd979faf980bbb572986d2d0445e3e`
- Frozen experience source: `checkpoint/iios-experience-x0-x6-release`
- Frozen experience release commit: `a1606248135122a4c8ed3cdfe900e4fd59effc50`
- Draft integration PR: #12

## Integration method

The experience release was **not merged directly** into Batch 8 because the branches had diverged. Instead, this integration branch was created from the latest Batch 8F head and the experience layer was brought in deliberately.

### Preserved from Batch 8F

- Entire `BACK END/` tree
- Existing Batch 8 scripts, including Batch 8F apply/smoke logic
- Batch 8 docs and README
- Existing frontend package lock and dependencies

### Integrated from X0–X6

- Additive experience components and styles under `FRONT END/src/`
- Five-room native shell: Factory / Research / Cases / Capital / Judgment
- X2 event/movement and desk-activity contracts
- X4 Judgment Bank surfaces
- X5 Thesis / Portfolio War Room and consequence matrix
- X6 Executive View
- Experience acceptance gate

### Shared frontend reconciliation

- `FRONT END/src/main.tsx`: deliberately switched from stacked legacy panels to `ExperienceNativeShell`. The shell retains the legacy Batch 8 underwriting workspace inside the Cases room.
- `FRONT END/package.json`: Batch 8 dependencies preserved; only `experience:acceptance` command added.
- `FRONT END/vite.config.ts`: Batch 8 React config preserved; preview proxy to backend 8002 added. It is inert unless `/__iios_api` is used.
- `FRONT END/src/previewApiBridge.ts`: isolated previews on 5188 and 5189 may use the same-origin proxy without changing backend CORS or execution authority.

### Backend conflict resolution

`BACK END/backend/paper_capital_api.py` from the experience branch was **not imported**.

The integration branch keeps the Batch 8F backend contract unchanged. Experience Capital/Executive surfaces already handle missing upstream capital prerequisites fail-closed, including current Batch 8 409 responses. This avoids overwriting newer Batch 8 capital logic.

## Safety invariants

1. No live-execution authority is introduced.
2. Paper / Shadow remains the represented execution mode.
3. Case movement remains canonical-event + case-identity gated.
4. Desk BUSY state remains event-derived.
5. Judgment publication remains human-gated.
6. Thesis integrity remains a read-only projection, not a second decision engine.
7. Batch Supervisor checkout is not the integration checkout.
8. Operator backend port 8002 must not be stopped or replaced during integration validation.

## Isolated validation tooling

The integration branch includes:

- `scripts/prepare_integration_validation.py` — creates a separate validation worktree at the exact remote integration head without switching the source checkout.
- `scripts/validate_integration_x0_x6.py` — runs the X0–X6 acceptance gate plus the Batch 8F engineering smoke and verifies operator/supervisor invariants afterward.
- `scripts/smoke_batch8f_isolated.py` — reuses the Batch 8F smoke logic on **port 8102**, never operator port 8002.
- `scripts/launch_integration_preview.py` — launches the integrated frontend on **port 5189** while reading the existing operator backend through the Vite proxy; it starts/stops no backend process.

Port allocation during integration validation:

- 8002 — existing operator backend; must remain untouched.
- 8102 — temporary isolated Batch 8F smoke backend; automatically stopped at the end of the smoke.
- 5188 — existing X0–X6 experience preview may continue running.
- 5189 — isolated integrated browser acceptance preview.

The dual-gate validator snapshots the process listening on 8002 and the Batch Supervisor branch/LaunchAgent state before validation and verifies they are unchanged afterward.

## Validation still required

The integration branch is **not merge-ready until all of these pass**:

1. X0–X6 experience acceptance gate in an isolated integration worktree.
2. Full frontend TypeScript/Vite build.
3. Experience-scoped ESLint.
4. Batch 8F engineering smoke on isolated port 8102.
5. Backend health and API contract verification.
6. Operator port 8002 and Batch Supervisor invariants unchanged after dual-gate validation.
7. Browser acceptance on 5189 for Factory / Research / Cases / Capital / Judgment / Executive View.
8. Confirm no live-execution or paper-safety permission changes.

## Important Batch 8F smoke note

The original `scripts/smoke_batch8f_live.py` defaults to owning port 8002 during its run. Do **not** execute it directly against the currently running operator backend/supervisor environment.

Integration validation must use `scripts/smoke_batch8f_isolated.py`, which redirects the same Batch 8F validation logic to port 8102.

## Merge rule

PR #12 must remain draft until both the Batch 8F engineering validation and X0–X6 experience acceptance gate pass on this integration branch, operator/supervisor isolation is verified, and final browser acceptance is complete.
