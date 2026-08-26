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
- `FRONT END/vite.config.ts`: Batch 8 React config preserved; isolated `5188 -> 8002` preview proxy added. It is inert unless `/__iios_api` is used.

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

## Validation still required

The integration branch is **not merge-ready until all of these pass**:

1. X0–X6 experience acceptance gate in an isolated integration worktree.
2. Full frontend TypeScript/Vite build.
3. Experience-scoped ESLint.
4. Batch 8F engineering smoke in an isolated backend environment.
5. Backend health and API contract verification.
6. Browser acceptance for Factory / Research / Cases / Capital / Judgment / Executive View.
7. Confirm no live-execution or paper-safety permission changes.

## Important Batch 8F smoke note

`scripts/smoke_batch8f_live.py` owns port 8002 during its run. Do **not** execute it against the currently running operator backend/supervisor environment. Run it only from an isolated integration checkout/backend when the operator lane can remain untouched.

## Merge rule

The integration PR must remain draft until both the Batch 8F engineering validation and X0–X6 experience acceptance gate pass on this integration branch, followed by human browser acceptance.
