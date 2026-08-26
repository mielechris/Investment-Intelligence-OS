# IIOS Experience X0–X6 — Release Checkpoint

Date: 2026-08-26

## Accepted release

- Working branch: `feature/iios-experience-x0-x1`
- Accepted release commit: `a1606248135122a4c8ed3cdfe900e4fd59effc50`
- Frozen checkpoint branch: `checkpoint/iios-experience-x0-x6-release`
- Release gate: `scripts/experience_release_gate.py`
- Gate result: PASS

The accepted commit is the exact code state that passed the X0–X6 release contract. The checkpoint branch must remain frozen as the recovery/reference point for this release.

## Accepted scope

- X0 — Canonical Factory Blueprint and room contracts
- X1 — Functional Command Center and truthful backend telemetry
- X2 — Living Factory movement/event contract and canonical event adapter
- X3 — Black/brass cinematic factory, eight specialist desks, MAX, formal five-room shell
- X4 — Judgment Bank workflow, human-approval/calibration surfaces, governed judgment library
- X5 — Portfolio & Thesis War Room, four-state thesis integrity projection, thesis-to-capital consequence matrix
- X6 — Executive / Showcase View with boardroom briefing and governed case journey

Operator rooms are frozen as:

`Factory → Research → Cases → Capital → Judgment`

Executive View is a mode layered over the same governed telemetry, not a sixth room.

## Release invariants

The accepted experience release preserves these invariants:

1. No visual state may fabricate READY, WORKING, BUSY, movement, or capital authority.
2. Case movement is permitted only from canonical events carrying sufficient case/audit identity.
3. Desk BUSY/RECENT/IDLE state is derived from real recent ledger events.
4. Paper / Shadow remains the only execution mode represented by the experience layer.
5. Live capital remains locked; the experience layer cannot grant live authority.
6. Judgment Bank publication remains human-gated and provenance-bound.
7. Thesis integrity is a read-only projection of governed monitor/re-underwrite state, not a second decision engine.
8. Operator and Executive modes share one active-case store.

## Release-gate acceptance

The X0–X6 acceptance gate passed the following checks:

- five-room Operator shell + Executive View present
- event movement remains case-identity gated
- desk activity is event-derived; no-event state is idle
- four-state thesis integrity model present
- Judgment Bank provenance surfaces present
- active-case state synchronized through one store
- live-capital authority remains locked
- full TypeScript / Vite build clean
- experience-scoped ESLint clean
- Batch Supervisor checkout isolated from experience worktree

## Integration status with Batch 8

Comparison against `feature/batch8-paper-portfolio` at checkpoint time:

- status: diverged
- experience checkpoint ahead by: 112 commits
- experience checkpoint behind by: 14 commits
- merge base: `c7aeafc216e455042e6bf0f372ecc3d23c384c78`

Therefore **do not merge the experience checkpoint directly into the running Batch 8 branch**.

The experience work contains mostly additive frontend/experience files, but there are shared-file changes requiring explicit integration review, including:

- `FRONT END/src/main.tsx`
- `FRONT END/package.json`
- `FRONT END/vite.config.ts`
- `README.md`
- `BACK END/backend/paper_capital_api.py`

`BACK END/backend/paper_capital_api.py` is the highest-risk shared change and must not be carried into the engineering lane automatically. It must be reconciled against the latest Batch 8 capital contract and tests.

## Safe integration plan

Integration must happen only after the current Batch 8 supervisor-driven engineering lane reaches a deliberate checkpoint.

### Phase 1 — Freeze engineering head

1. Record the accepted Batch 8 branch and commit.
2. Confirm Batch Supervisor has no pending autonomous action that would mutate the integration target.
3. Run the Batch 8 engineering/readiness gate and preserve its output.

### Phase 2 — Create a fresh integration branch

Create a new branch from the **latest accepted Batch 8 engineering head**, not from the experience branch.

Recommended name:

`integration/iios-experience-x0-x6`

### Phase 3 — Integrate in controlled layers

1. Bring in additive experience frontend files and styles.
2. Reconcile `main.tsx`, `package.json`, and `vite.config.ts` manually against the latest engineering branch.
3. Reconcile shared backend changes separately; do not overwrite Batch 8 capital logic.
4. Preserve all live-capital, paper/shadow, risk, and supervisor invariants.

### Phase 4 — Dual-gate validation

The integration branch must pass both:

- the latest Batch 8 engineering/readiness gate
- `python3 scripts/experience_release_gate.py`

Additionally verify:

- backend API startup and health
- five-room Operator mode
- Executive View
- active-case synchronization
- canonical event movement
- Capital fail-closed behavior
- Judgment human-approval gate
- no live-execution authority changes

### Phase 5 — Human browser acceptance

Before merge, manually review:

- Factory
- Research
- Cases
- Capital
- Judgment
- Executive View

Only after both automated gates and browser acceptance are clean should the integration branch be eligible for merge.

## Freeze rule

`checkpoint/iios-experience-x0-x6-release` is a frozen recovery branch. Do not continue feature work on it and do not force-update it.

Future experience development continues on a new post-release branch or the existing working experience branch after this checkpoint is recorded.
