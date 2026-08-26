# IIOS Experience Execution Plan — X0 through X6

## Working Model

The experience program runs in parallel with the intelligence-engineering program. Engineering owns truth, evidence, governance, and state. Experience owns navigation, visualization, interaction, identity, and presentation. Experience must never invent state that the backend does not expose.

Active experience branch: `feature/iios-experience-x0-x1`

Base engineering branch at kickoff: `feature/batch8-paper-portfolio`

## Parallelization Rule

- Batch 8 engineering may continue independently.
- X0/X1 may be built and tested without changing Batch 8 backend behavior.
- X2 may begin once X1 has reliable activity/state contracts.
- X3 art direction may be designed in parallel, but final animation hooks wait for X2 truth bindings.
- X4 and X5 can prototype information architecture while X2/X3 progress.
- X6 begins only after X3–X5 are coherent enough to present as one product.
- Merge into the active engineering line only after frontend build, regression checks, and visual review.

---

## X0 — Factory Blueprint

**Status: IN PROGRESS**

### Build now

- canonical factory zone registry
- source-of-truth binding for each zone
- room categories and navigation hierarchy
- explicit truth rules
- desktop floor-plan geometry
- responsive fallback hierarchy

### Current implementation

- `FRONT END/src/experienceBlueprint.ts`
- `FACTORY_ZONES`
- `EXPERIENCE_PHASES`
- `EXPERIENCE_TRUTH_RULES`

### Done when

- every visible room has a real system purpose
- every operational indicator identifies a real source of truth
- no fake READY / WORKING state exists
- all X1–X6 views can reference the same canonical zone registry

---

## X1 — Functional Command Center

**Status: FIRST IMPLEMENTATION WRITTEN**

### Build now

- system online/offline
- backend version
- paper/shadow status
- live-capital lock status
- safety invariant status
- agent count
- active cases
- recent event count
- recent desk completions
- room occupancy/activity when available
- validation readiness/blockers
- provider/job health as endpoints become available

### Current implementation

- `FRONT END/src/ExperienceCommandCenter.tsx`
- live polling of `/system/status`, `/factory-room/status`, `/agents`
- five-second refresh
- unknown/offline fail-honest rendering
- canonical X0 map rendered beside live X1 telemetry
- `scripts/apply_experience_x0_x1.py` safe integration gate

### Next X1 work

- background-job registry surface
- provider health matrix
- branch/build identity from backend status
- ingestion freshness
- experiment state cards
- clickable room navigation
- operator alerts and degraded-state explanations

### Done when

Routine operation no longer requires watching terminal output for basic system health, job progress, case movement, or safety state.

---

## X2 — Living Factory Floor

**Status: CONTRACT DESIGN NEXT**

### Goal

Turn workflow state into physical movement through the factory without creating simulated activity.

### Required state model

- case created
- evidence collecting
- agent desk assigned
- agent active
- agent complete
- blocked / insufficient evidence
- committee queued
- committee active
- committee complete
- risk inspection
- capital / sizing / authorization
- paper execution
- monitoring / re-underwrite
- closed / postmortem

### Visual behaviors

- case tokens physically move room-to-room
- room lights change only from real state
- agent characters animate only during real jobs
- blocked cases visibly stop at the blocking room
- dissent remains visible at Committee
- execution bay remains visibly locked to paper/shadow

### Done when

A user can understand where every active case is in the process by looking at the floor without reading logs.

---

## X3 — Art / Mob / Neon / MAX Identity

**Status: ART DIRECTION DEFINED; PRODUCTION AFTER X2 CONTRACT**

### Visual language

- cinematic industrial headquarters
- dark steel / glass / concrete factory architecture
- neon market-data accents
- old-school deal-room / mob-family attitude
- premium rather than cartoonish
- MAX the bulldog as discipline / risk mascot
- adult irreverent humor as environmental flavor and Easter eggs

### Rules

- humor never replaces risk or evidence labels
- decorative alarms never imply real alerts
- MAX reactions must map to actual state when used operationally
- external intelligence has a visibly different aesthetic from governed native evidence
- motion is restrained enough for all-day professional use

### Initial art assets

- factory establishing view
- room visual language guide
- eight agent silhouettes / desk identities
- MAX neutral / alert / blocked / approved-paper states
- committee-room visual
- risk-inspection visual
- paper-execution bay visual
- Judgment Bank library visual

---

## X4 — Judgment Bank Experience

**Status: INFORMATION ARCHITECTURE READY TO START IN PARALLEL**

### Core views

- Interview Library
- person / operator profile
- transcript timeline
- extracted principles
- judgment cards
- decision trees
- dissent / contradiction view
- validation history
- agent scorecards
- principle provenance

### Experience concept

The Judgment Bank should feel like a private members-only library / archive inside the factory: quieter, warmer, more intimate than the trading floor.

### Done when

A user can move from a person, to what they said, to the principle extracted, to where it influenced research, to how that judgment performed later.

---

## X5 — Portfolio & Thesis War Room

**Status: INFORMATION ARCHITECTURE DEFINED; DATA CONTRACT DEPENDS ON PORTFOLIO / THESIS ENGINE**

### Core views

- paper NAV / cash / positions
- exposure and concentration
- position-level thesis contracts
- current return vs thesis integrity
- catalysts
- explicit falsifiers
- evidence deltas
- thesis state: INTACT / EARLY_BUT_INTACT / MATERIAL_CHANGE / THESIS_BROKEN / INSUFFICIENT_EVIDENCE / CLOSED
- committee history
- confidence history
- re-underwrite history
- timing vs thesis correctness

### Key visual rule

P&L and thesis integrity must be visually separated. A red return does not automatically mean a broken thesis; a green return does not prove the thesis is healthy.

---

## X6 — Executive / Showcase Edition

**Status: PLANNED**

### Goal

Create the polished top-level version used for daily command, executive review, demonstrations, and investor-style storytelling.

### Modes

- Operator Mode — dense live state and controls
- Executive Mode — concise system / portfolio / thesis overview
- Showcase Mode — guided factory tour with live-state snapshots and narrative explanations

### Required features

- one-screen health summary
- factory overview
- portfolio / thesis summary
- active research queue
- top evidence changes
- Committee decisions
- risk / safety posture
- Judgment Bank highlights
- validation / learning metrics
- provenance links for every major claim

### Done when

The system can be shown to a sophisticated outsider without terminals, hidden context, or verbal explanation being required to understand what IIOS is doing and why.

---

# Immediate Work Order

1. X0 canonical blueprint contract — build now.
2. X1 live Command Center first pass — build now.
3. Validate X0/X1 against current Batch 8 frontend and endpoints.
4. Design X2 workflow-state event contract.
5. Start X3 concept art / identity system in parallel with X2 engineering.
6. Prototype X4 information architecture using existing Interview Portal / Judgment Bank data.
7. Prototype X5 War Room against existing paper-portfolio and Thesis Integrity contracts.
8. Consolidate into X6 only after the underlying rooms are truthful and useful.

# Safety / Governance

This experience track does not change trading authority. It must preserve paper/shadow mode and must not add live execution, automatic trade authority, paper-order permission beyond existing governed mechanisms, or visual controls that imply unsupported authority.
