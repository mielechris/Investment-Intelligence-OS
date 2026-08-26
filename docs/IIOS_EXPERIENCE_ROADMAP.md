# IIOS Experience Roadmap

## Purpose

Build the IIOS front end as a **live Intelligence Factory** rather than a conventional financial dashboard. Every visual room, character, indicator, and animation must correspond to a real governed system state. The art is part of the product experience, but it must never obscure evidence quality, uncertainty, safety state, or auditability.

## Current Engineering Anchor

As of Batch 8D, the active feature branch is `feature/batch8-paper-portfolio`. Batch 8D is integrating **Kimi Research & Swarm Intelligence** into the governed IIOS research stack. The experience track begins now in parallel with engineering so the visual architecture is ready when Batch 8 closes.

The current front end already contains working Factory UI foundations, including `FactoryRoom`, Interview Portal, evidence panels, institutional intelligence, decision history, and other live research views. The experience roadmap should evolve these working components rather than replace them with disconnected concept art.

---

# North Star

Opening IIOS should feel like entering a private, cinematic investment headquarters:

- industrial intelligence factory
- neon / dark-market atmosphere
- mob-family / old-school deal-room attitude
- Wolf-of-Wall-Street energy without sacrificing governance
- adult, irreverent humor used as personality and Easter eggs
- MAX the bulldog as the factory mascot and discipline symbol
- agents represented as recognizable workers / specialists with their own rooms
- live movement through the factory reflects actual workflow state
- serious financial data remains crisp, readable, and professional

The experience should be memorable enough to feel like art and trustworthy enough to run an investment process.

---

# Experience Track

## X0 — Factory Blueprint — START NOW

### Deliverables

Create the canonical floor plan and navigation hierarchy before heavy visual implementation.

Rooms / zones:

1. **Intelligence Floor** — overall factory map and live system state.
2. **Agent Desks / Rooms** — one recognizable space per core agent.
3. **Research Annex** — external research systems such as Grok and Kimi, visually separated from governed native evidence.
4. **Investment Committee Room** — synthesis, dissent, confidence, disposition.
5. **Skeptic / Red Room** — strongest counter-case and thesis attack surface.
6. **Risk Inspection** — deterministic safety / risk gate.
7. **Paper Execution Bay** — paper-only order state and authorization lineage.
8. **Portfolio Office** — positions, exposures, concentration, thesis state, P&L context.
9. **Thesis Integrity Room** — intact vs early vs material change vs broken.
10. **Judgment Bank / Interview Library** — Jesse, Matt, and future professional interviews; searchable principles and judgment cards.
11. **Evidence Warehouse** — source lineage, freshness, hard data, filings, news, insider, institutional, macro, policy.
12. **Control Room** — system health, jobs, ingestion, provider health, schedules, experiment status.

### Acceptance Criteria

- every room maps to a real endpoint / state / object
- no decorative room exists without a defined system purpose
- one-screen factory blueprint works on desktop
- user can move from factory overview to a case without terminal use

---

## X1 — Functional Command Center

### Goal

Replace terminal babysitting with a live operator dashboard.

### Required Views

- system online / offline
- active branch / build version
- provider health
- active research jobs
- agent state: idle / researching / blocked / complete / failed
- current case queue
- committee-ready cases
- evidence gaps
- paper portfolio summary
- safety state always visible
- recent alerts / failures

### Non-Negotiable Safety UI

The following states must always be visually explicit and never hidden behind theme art:

- `paper_mode`
- `auto_trade_authority`
- `paper_order_permission`
- `trade_execution_permission`
- `live_execution`

Humor must never appear inside critical safety or error messaging.

---

## X2 — Living Factory Floor

### Goal

Turn the command center into the visual Intelligence Factory.

### Behavior

- agents occupy their rooms
- active agents visibly work when a governed job is running
- evidence moves toward the relevant desk / room
- completed research moves toward Committee
- blocked research visually stops at the corresponding gate
- Committee state changes only from actual committee objects
- Risk Inspection animates only when a real risk inspection occurs
- Paper Execution Bay never visually implies a live order
- external research sources remain visually distinct from admitted governed evidence

### Agent Identity

Each agent receives:

- name / title
- role
- visual silhouette / wardrobe / room identity
- signature mannerism
- clearly defined data lanes
- current task
- last completed task
- confidence / disagreement state where applicable

Character design must make the eight-agent team instantly understandable without turning analytical output into a cartoon.

---

## X3 — Art & Identity Pass

### Visual Direction

- dark industrial architecture
- neon signage
- glass offices / factory catwalks / deal-room elements
- subtle casino / finance references where appropriate
- cinematic lighting and depth
- restrained use of red for actual warnings so warning semantics remain trustworthy
- MAX appears throughout as mascot / foreman / discipline icon

### Mob / Family Tone

Use the mob-inspired concept as a **visual and cultural motif**, not as literal criminal behavior. Themes:

- loyalty to process
- reputation
- discipline
- hierarchy of review
- everyone has a job
- nobody skips the Committee / Risk chain

### Humor Layer

Humor should live in:

- wall signs
- loading states
- room plaques
- MAX reactions
- harmless Easter eggs
- optional flavor copy

Tone can be adult, dark, edgy, and irreverent. It must never contaminate evidence text, regulatory / risk data, audit records, safety states, or professional exports.

Example style: absurd mob/deal-room one-liners, marinara jokes, golf jokes, market pain jokes, and MAX acting like the foreman who has seen too much.

---

## X4 — Judgment Bank Experience

### Goal

Make human judgment feel like a first-class asset inside the factory.

### Experience

The Interview / Judgment area should resemble a private archive or members-only library.

Show:

- interviewee
- expertise
- session timeline
- extracted principles
- decision trees
- judgment cards
- contradictions / dissent
- related cases
- where a principle influenced research
- validation history

Human judgment is reference intelligence. It never silently becomes automatic trade authority.

---

## X5 — Portfolio & Thesis War Room

### Goal

Create the daily-investor view after the factory becomes operational.

### Portfolio Office

Show:

- paper positions
- current exposures
- concentration
- sector / factor overlap
- thesis age
- entry thesis vs current thesis
- catalysts
- current return as context
- next required evidence
- upcoming events

### Thesis Integrity Room

Visually separate **price performance** from **thesis integrity**.

Primary states:

- `INTACT`
- `EARLY_BUT_INTACT`
- `MATERIAL_CHANGE`
- `THESIS_BROKEN`
- `INSUFFICIENT_EVIDENCE`
- `CLOSED`

The user should be able to see why the system believes a thesis is intact or broken without reading raw logs.

---

## X6 — Executive / Showcase Edition

### Goal

Turn IIOS into something that can be shown to an investor, operator, advisor, or future institutional client without exposing developer plumbing.

### Modes

- **Operator Mode** — full controls, evidence lineage, research jobs, diagnostics.
- **Investment Mode** — factory, cases, Committee, portfolio, thesis integrity.
- **Executive Mode** — simplified high-level intelligence and portfolio story.
- **Showcase Mode** — guided cinematic factory walkthrough using real or sandbox data.

---

# Implementation Order

## During Batch 8D / remainder of Batch 8

- freeze the factory room taxonomy
- map current endpoints / objects to rooms
- define agent identities and room ownership
- define visual state vocabulary
- define design tokens and warning semantics
- keep front-end regressions green while Kimi / research layers are being integrated

## Immediately After Batch 8

1. Build X1 Functional Command Center.
2. Wire real-time / polling state into factory overview.
3. Build X2 Living Factory Floor.
4. Apply X3 Art & Identity pass without changing analytical semantics.
5. Deepen Judgment Bank and Portfolio / Thesis rooms.

The first usable visual should arrive before the final cinematic polish. Function first, identity from day one, immersion progressively layered.

---

# Visual Truth Rules

1. **No fake activity.** An agent only looks active when a real job is active.
2. **No fake confidence.** Visual confidence must come from a governed object.
3. **No fake evidence.** Decorative social / research content cannot be mistaken for admitted evidence.
4. **No fake trading.** Paper execution must never look like live brokerage execution.
5. **No hidden failures.** Provider, ingestion, or agent failures must surface visibly.
6. **No art over truth.** Readability and evidence lineage override aesthetics.
7. **No humor in safety-critical states.** Risk, authorization, failure, and execution permissions remain serious.
8. **Auditability survives the art layer.** Every meaningful visual state must be explainable from persisted data.

---

# Definition of Done

The IIOS Experience Track is complete when the user can operate the normal research and paper-investment workflow without needing VS Code terminals for routine use, while still being able to drill from any visual state down to the evidence, judgment, committee decision, safety gate, and audit lineage that produced it.

The finished product should feel like a piece of interactive investment art on the surface and a governed intelligence operating system underneath.
