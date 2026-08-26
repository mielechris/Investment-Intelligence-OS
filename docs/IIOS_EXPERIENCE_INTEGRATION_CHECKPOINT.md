# IIOS X0–X6 Experience Integration Checkpoint

Date: 2026-08-26

## Integration branch

- Branch: `integration/iios-experience-x0-x6`
- Base engineering branch: `feature/batch8-paper-portfolio`
- Base engineering commit at branch creation: `db379c7dddbd979faf980bbb572986d2d0445e3e`
- Frozen experience source: `checkpoint/iios-experience-x0-x6-release`
- Frozen experience release commit: `a1606248135122a4c8ed3cdfe900e4fd59effc50`

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
- `FRONT END/vite.config.ts`: Batch 8 React config preserved; isolated preview proxy added. It is inert unless `/__iios_api` is used.

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

## Automated integration validation — PASS

The isolated integration validator passed on 2026-08-26.

- X0–X6 experience gate: PASS
- Full TypeScript / Vite build: PASS
- Experience-scoped ESLint: PASS
- Batch 8F engineering smoke on isolated port 8102: PASS
- Batch 8F verdict: `SCALE_VALIDATION_READY`
- Batch Supervisor branch unchanged: PASS
- Batch Supervisor LaunchAgent remained loaded: PASS
- Validation checkout had no tracked mutations: PASS
- Live execution authority: `FALSE`
- Committee / Risk override: `FALSE`
- Capital / trade authority: `FALSE`

The operator-port invariant reported `8002 PID(s) unchanged -> none`. This proves the validator did not stop or replace a process on 8002, but it also means a live operator backend was not present during this validation. Backend API/health therefore remains a separate browser-acceptance prerequisite.

## Port isolation plan

- `8002`: operator/integration browser backend. Validation never kills or replaces it.
- `8102`: temporary isolated Batch 8F engineering smoke backend.
- `5188`: existing experience preview may remain running.
- `5189`: integrated browser-acceptance preview.

## Remaining validation

The integration branch is **not merge-ready until all of these pass**:

1. Start/verify the intended backend on port 8002 without disturbing the Batch Supervisor.
2. Verify backend health and API contract.
3. Launch integrated browser preview on port 5189.
4. Human browser acceptance for Factory / Research / Cases / Capital / Judgment / Executive View.
5. Confirm browser telemetry remains truthful/fail-closed and no live-execution permission is exposed.

## Merge rule

Draft PR #12 must remain draft until backend health and human browser acceptance are clean. Only then may it be marked ready for review/merge.
