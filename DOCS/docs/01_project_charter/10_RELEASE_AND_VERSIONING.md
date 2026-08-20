# Investment Intelligence OS
## Release and Versioning Standard — v0.1

**Purpose:** Make every material change traceable, reversible, and understandable.

---

## 1. Version Format

IIOS uses semantic-style versions:

`MAJOR.MINOR.PATCH`

Example:

`0.1.0`

### Major

Increase when:

- architecture or governance changes incompatibly;
- live authority changes;
- canonical schemas break compatibility;
- system purpose materially changes;
- institutional operating model is introduced.

### Minor

Increase when:

- a new backward-compatible capability is added;
- a new agent, connector, domain, or dashboard module is added;
- a specification receives a material expansion;
- a new paper strategy is promoted.

### Patch

Increase when:

- a backward-compatible defect is fixed;
- documentation is clarified;
- tests are improved;
- a parser is corrected without changing the public contract;
- monitoring or logging is improved.

Versions below `1.0.0` are pre-production and may evolve quickly, but changes must still be recorded.

---

## 2. Document Versioning

Each governing document includes:

- title;
- version;
- status;
- date;
- owner;
- approval state;
- change summary.

Do not overwrite an approved version without history.

Use names such as:

- `PROJECT_CHARTER_v0.1.md`
- `PROJECT_CHARTER_v0.2.md`

or retain the stable filename and rely on Git history plus a document version field.

The selected repository convention must be recorded in an ADR.

---

## 3. Environments

### Development

Purpose:

- local coding;
- unit tests;
- fixtures;
- synthetic data;
- experimental prompts.

Restrictions:

- no live trading;
- no production credentials;
- no unapproved sensitive data.

### Test

Purpose:

- integration tests;
- deterministic replay;
- failure simulation;
- migration tests;
- evaluation suites.

Restrictions:

- paper and synthetic state only.

### Paper

Purpose:

- forward paper decisions;
- realistic simulated orders;
- daily operating routine;
- performance and calibration measurement.

Restrictions:

- no live-money order routing;
- clearly labeled as paper.

### Live

Status in V1:

- disabled;
- not deployed;
- not authorized.

A future live environment must be technically and permissionally separate from paper mode.

---

## 4. Branching

Recommended starting pattern:

- `main` — stable approved state
- `develop` — integrated work awaiting release
- `feature/<ticket-id>-description` — isolated work
- `fix/<ticket-id>-description` — defect fix
- `docs/<ticket-id>-description` — documentation
- `release/<version>` — release preparation
- `hotfix/<version>` — urgent approved production fix when applicable

For a one-person V1, this may be simplified, but `main` must remain a known-good state.

---

## 5. Commit Convention

Recommended format:

`type(scope): description [ticket-id]`

Examples:

- `docs(charter): add V1 success gates [T002]`
- `feat(ingestion): add presidential-actions connector [T031]`
- `test(risk): verify stale-feed stand-down [T114]`
- `fix(schema): preserve market_available_at timezone [T024]`

Suggested types:

- `feat`
- `fix`
- `docs`
- `test`
- `refactor`
- `chore`
- `build`
- `ci`
- `perf`
- `security`

---

## 6. Release Gate

A release requires:

- included-ticket list;
- passing tests;
- migration review;
- configuration review;
- secret scan;
- data-boundary review;
- risk review;
- known-limitations list;
- release notes;
- rollback plan;
- backup verification;
- Engineering Log entry;
- Decision Register update for material choices;
- version tag;
- explicit confirmation that live trading remains disabled in V1.

---

## 7. Model and Prompt Versioning

Every production or paper decision must record:

- provider;
- model name;
- model version or provider identifier;
- prompt template version;
- tool permissions;
- retrieval configuration;
- temperature or equivalent settings where relevant;
- evaluation suite version;
- deployment date;
- cost and latency where available.

A model-provider change is not a transparent implementation detail. It requires evaluation.

---

## 8. Data and Schema Versioning

Canonical objects must include schema versions.

Breaking changes require:

- migration;
- compatibility analysis;
- replay test;
- affected-service review;
- updated fixtures;
- release note;
- ADR when material.

Raw data is immutable. Corrections create new versions rather than silently rewriting history.

---

## 9. Strategy Versioning

Every strategy or hypothesis module must have:

- strategy ID;
- version;
- hypothesis;
- feature set;
- parameters;
- research dataset version;
- test-period definition;
- cost assumptions;
- benchmark;
- promotion status;
- retirement status;
- review date.

Do not replace a failed strategy result with a newly tuned result under the same version.

---

## 10. Rollback

A release is not ready unless the team knows how to return to the previous known-good state.

Rollback planning must cover:

- code;
- configuration;
- database migrations;
- models and prompts;
- scheduled jobs;
- connectors;
- paper portfolio state;
- dashboard;
- secrets.

A rollback must never erase the audit record.

---

## 11. Release Notes Template

# IIOS Release X.Y.Z

**Release date:**  
**Status:**  
**Approved by:**  
**Operating mode:** Development / Test / Paper / Live  

## Summary

## Added

## Changed

## Fixed

## Removed

## Security

## Data and Schema Changes

## Model and Prompt Changes

## Known Limitations

## Risk Changes

## Migration Instructions

## Rollback Instructions

## Related Tickets

## Related ADRs

## Verification Evidence
