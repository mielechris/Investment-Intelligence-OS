# Investment Intelligence OS
## Architecture Principles and Guardrails — v0.1

---

## 1. Modular Monolith First

V1 shall be implemented as a modular monolith with strict internal boundaries.

A module must expose an application interface. Other modules may not write directly into its tables or bypass its invariants.

The architecture may use multiple runtime processes, but process separation does not automatically create a separate service.

Service extraction requires evidence such as:

- independent scaling pressure;
- distinct security boundary;
- independent deployment need;
- materially different availability requirement;
- team ownership boundary;
- data-locality requirement;
- unacceptable coupling after measurement.

---

## 2. PostgreSQL Is the Transactional System of Record

All durable operational state must be committed to PostgreSQL or referenced from PostgreSQL to immutable object storage.

Do not rely on:

- in-memory state;
- browser state;
- cache-only state;
- model conversation history;
- untracked files;
- undocumented spreadsheets.

---

## 3. Raw Data Is Immutable

The system preserves the original retrieved payload before transformation.

Corrections create new records or versions.

A parser may be rerun against a raw record without refetching or rewriting the source.

---

## 4. Time Is a First-Class Dimension

Every time-sensitive object must distinguish the relevant clocks.

At minimum, the architecture supports:

- publication time;
- effective time;
- observation time;
- market-availability time;
- valid-from and valid-to where state changes over time;
- system-recorded time.

Historical queries must specify an “as known at” cutoff.

---

## 5. Contracts Before Implementations

Each module, connector, agent, and adapter needs:

- typed input;
- typed output;
- version;
- error contract;
- idempotency behavior;
- authorization boundary;
- logging requirements;
- acceptance tests.

Implementation details may change without breaking governed contracts.

---

## 6. Deterministic Controls Surround Probabilistic Intelligence

AI-generated output never directly changes:

- portfolio cash;
- positions;
- risk limits;
- environment mode;
- source permissions;
- order authorization;
- constitutional rules.

AI output enters typed validation, evidence checks, committee review, and deterministic risk controls.

---

## 7. Evidence Lineage Is Mandatory

No material claim or decision may exist without lineage.

The required chain is:

```text
source → raw record → normalized object → evidence → claim
→ reasoning → thesis → decision → risk → execution or no-trade → outcome
```

Missing lineage invalidates the downstream object.

---

## 8. Safe Failure Beats Partial Activity

When critical state is unreliable, the system must:

- stop creating new risk;
- preserve current state;
- surface the failure;
- allow inspection;
- retry safely;
- avoid duplicate writes;
- recover through replay.

Silent degradation is prohibited for risk-critical paths.

---

## 9. No-Trade Is a First-Class Result

The architecture must support no-trade at:

- source-quality review;
- reasoning;
- agent analysis;
- committee;
- risk;
- execution readiness;
- operational health.

The system must not manufacture activity to appear useful.

---

## 10. Simplicity Must Be the Default

A new technology, model, service, data source, or agent must justify itself.

It must improve at least one of:

- correctness;
- calibration;
- risk control;
- decision quality;
- reliability;
- cost;
- speed;
- maintainability;
- useful diversification.

Otherwise the simpler baseline remains.

---

## 11. Point-in-Time Research Is Non-Negotiable

Research must use data available at the simulated decision time.

The architecture must prevent:

- revised macro data leaking backward;
- filing dates being confused with transaction dates;
- future constituents entering historical universes;
- later labels entering feature generation;
- future event classifications entering prior tests.

---

## 12. Idempotency Is Required

Every retriable command or job must have an idempotency key.

Rerunning the same work must:

- return the existing result;
- create a new explicit version;
- or safely replace an incomplete derived artifact.

It must not silently duplicate decisions, orders, fills, or source records.

---

## 13. At-Least-Once Delivery, Exactly-Once Effects

The architecture assumes jobs and events may be delivered more than once.

Reliability is achieved through:

- immutable event IDs;
- unique constraints;
- inbox records;
- idempotent handlers;
- transactional outbox;
- replay-safe projections.

Do not claim network-level exactly-once delivery.

---

## 14. Vendor Neutrality Through Adapters

External providers are accessed through stable internal interfaces.

Adapters include:

- source connectors;
- market-data providers;
- model providers;
- embedding providers;
- paper brokers;
- future live brokers;
- object storage;
- observability exporters.

Vendor-specific fields remain in raw metadata, not in canonical domain contracts.

---

## 15. Bounded Agents, Bounded Tools, Bounded Time

Every agent run has:

- explicit task;
- approved data scope;
- approved tools;
- maximum steps;
- maximum tokens or cost;
- timeout;
- structured output;
- evidence requirement;
- abstention option;
- versioned prompt and model.

Open-ended autonomous loops are not permitted in V1.

---

## 16. Risk Is Independent

The Risk Engine receives committee candidates but owns its own evaluation.

It must not trust committee confidence as sufficient evidence for size.

Risk logic is deterministic, tested, versioned, and separately auditable.

---

## 17. Browser Logic Is Not Authoritative

The frontend may:

- display;
- filter;
- sort;
- request actions;
- maintain temporary interface state.

The frontend may not become the sole implementation of:

- portfolio calculations;
- exposure limits;
- paper accounting;
- source trust;
- decision lineage;
- permissions;
- environment mode.

---

## 18. Observability Is Part of the Feature

Every important workflow must emit:

- structured logs;
- metrics;
- trace or correlation identifiers;
- job status;
- error classification;
- duration;
- version context.

An unobservable workflow is incomplete.

---

## 19. Reproducibility Over Convenience

A research or decision run must preserve:

- source cutoff;
- data versions;
- code commit;
- schema versions;
- model and prompt versions;
- parameters;
- random seed where relevant;
- execution assumptions;
- output artifacts.

---

## 20. Security by Least Privilege

Each process, connector, model, and user receives only the permissions required.

Secrets are externalized.

Tools are allow-listed.

Sensitive operational actions require explicit authorization.

---

## 21. Append History; Do Not Erase It

Material changes produce new versions.

Do not erase:

- failed hypotheses;
- rejected strategies;
- dissent;
- prior model outputs;
- previous risk decisions;
- paper trades;
- postmortems;
- architecture decisions.

History is a learning asset.

---

## 22. Promotion Is Evidence-Based

The promotion ladder is:

```text
idea
→ registered hypothesis
→ exploratory research
→ controlled historical test
→ holdout or walk-forward test
→ forward paper observation
→ limited approved pilot
→ broader deployment
```

Skipping stages requires a formal exception and risk decision.

---

## 23. Architecture Review Questions

Before adding or changing a component, ask:

1. What authoritative state does it own?
2. What contract does it expose?
3. What happens if it runs twice?
4. What happens if it fails halfway?
5. Can it be replayed?
6. Can its output be traced?
7. Can it abstain or fail safe?
8. What permissions does it need?
9. What is the simple baseline?
10. How will we know it adds value?
11. What must change to remove it later?
12. Does it preserve the Constitution?
