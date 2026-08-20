# Investment Intelligence OS
## Project Charter & Governance Folder — v0.1

**Build date:** August 20, 2026  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading  
**Current user:** Single founder/operator  
**Architecture posture:** Personal-first. Institution-ready. Evidence-bound. Risk-controlled.

---

## Purpose of This Folder

This folder defines what the Investment Intelligence OS (IIOS) is, what Version 1 is allowed to do, how decisions are governed, and what must be true before the project can move forward.

These documents are not filler. They are the operating contract for the codebase.

When product ideas, agent outputs, market narratives, or implementation shortcuts conflict with this folder, this folder controls unless a documented architecture decision formally changes it.

---

## Document Order

| Order | File | Purpose |
|---:|---|---|
| 1 | `01_PROJECT_CHARTER.md` | Defines the mission, objectives, scope, deliverables, governance, and success criteria. |
| 2 | `02_SYSTEM_CONSTITUTION.md` | Defines the non-negotiable principles and guardrails every component must obey. |
| 3 | `03_V1_SCOPE_AND_SUCCESS_GATES.md` | Defines exactly what V1 includes, excludes, and must prove. |
| 4 | `04_SYSTEM_MAP.md` | Shows how sources, data, reasoning, agents, risk, paper execution, and learning connect. |
| 5 | `05_DECISION_REGISTER.md` | Records material product and architecture decisions and why they were made. |
| 6 | `06_ENGINEERING_LOG.md` | Records what was built, tested, learned, blocked, and changed during each work session. |
| 7 | `07_DEFINITION_OF_DONE.md` | Defines what “complete” means for documents, code, connectors, agents, tests, and releases. |
| 8 | `08_RISK_REGISTER.md` | Tracks the main ways the project can fail and the controls that address them. |
| 9 | `09_PUBLIC_INFORMATION_AND_MNPI_BOUNDARY.md` | Defines what information may and may not enter the system. |
| 10 | `10_RELEASE_AND_VERSIONING.md` | Defines version numbers, release gates, environments, change logs, and rollback. |
| 11 | `11_MASTER_GLOSSARY.md` | Establishes the common language used throughout IIOS. |
| 12 | `12_ADR_TEMPLATE.md` | Provides the standard template for future architecture decision records. |

---

## Document Precedence

When two documents appear to conflict, use this order:

1. `02_SYSTEM_CONSTITUTION.md`
2. Approved architecture decision records
3. `01_PROJECT_CHARTER.md`
4. `03_V1_SCOPE_AND_SUCCESS_GATES.md`
5. `08_RISK_REGISTER.md`
6. Technical specifications
7. Tickets and implementation notes

A lower-level document may add detail, but it may not quietly weaken a higher-level control.

---

## Update Rules

Every material change must include:

- a version change;
- a date;
- the person or role approving it;
- a reason for the change;
- affected documents, specifications, tests, and code;
- a review of risk and backward compatibility;
- an entry in the Decision Register and Engineering Log.

Do not silently overwrite a governing decision.

---

## Current Build Sequence

The immediate objective is one auditable vertical slice:

`official public source → immutable raw record → normalized event → evidence → world model → causal chain → specialist agents → committee decision → risk review → paper order or no-trade → dashboard → decision journal`

The first slice must include:

- one White House or presidential-action source;
- one Federal Reserve or macroeconomic source;
- one non-policy source such as SEC, NOAA, USDA, or EIA;
- policy, macro, and skeptic views;
- an explicit no-trade path;
- a complete audit trail.

---

## Founder Operating Rule

**Do not start the day by asking, “What should I buy?”**

Start by asking:

1. What changed?
2. What is the evidence?
3. What is still uncertain?
4. What mechanisms could transmit the change into markets?
5. What contradicts the leading explanation?
6. Is there a testable thesis?
7. Is the expected opportunity worth the risk?
8. Should the correct action be long, short, watch, avoid, or no-trade?

That sequence is the foundation of IIOS.
