# SPEC-027 — Corporate Relationship Mapping

**Priority:** P1  
**Owner:** Corporate Intelligence  
**Status:** Approved V0.1 baseline  
**Package:** 03 — Specifications

---

## 1. Purpose

Map companies to parents, subsidiaries, suppliers, customers, facilities, technologies, commodities, governments, and geographies.


## Cross-Cutting Requirements

This specification inherits the following requirements unless explicitly strengthened:

- public or properly licensed information only;
- point-in-time correctness;
- immutable raw provenance;
- typed and versioned contracts;
- idempotent retriable operations;
- structured logs and correlation IDs;
- bounded AI authority;
- deterministic risk enforcement;
- paper-only V1;
- no-trade and stand-down support;
- historical versions preserved;
- Definition of Done from Package 01.


## 2. Functional Requirements

1. Parent/subsidiary.
2. Supplier/customer.
3. Partners.
4. Competitors.
5. Facilities.
6. Technology dependencies.
7. Commodity dependencies.
8. Government contracts.
9. Revenue geography.
10. Capex programs.

## 3. Inputs

The component MUST accept only versioned, typed inputs from approved upstream interfaces. Inputs MUST carry the environment, relevant source cutoff, correlation ID, and lineage references required by the architecture.

## 4. Outputs

Primary durable outputs:

- `CorporateRelationship`
- `RelationshipEvidence`

Outputs MUST be immutable or explicitly versioned where their interpretation can change. Material outputs MUST emit an audit or domain event.

## 5. State and Versioning

- State transitions MUST be explicit and validated.
- Material revisions MUST create new versions rather than erase history.
- Historical decisions MUST continue pointing to the versions used at the time.
- Replay MUST be safe and MUST NOT duplicate operational effects.

## 6. Security and Governance

- Authorization MUST be enforced in the backend.
- Quarantined or prohibited information MUST be excluded.
- Secrets MUST NOT appear in source control, logs, or model prompts.
- AI-generated data MUST be schema validated before durable promotion.
- The component MUST fail safe when constitutional or risk-critical preconditions are not met.

## 7. Failure Behavior

Failures MUST be classified as one of:

- retryable;
- permanent;
- quarantined;
- business rejection/no-trade;
- critical stand-down.

Retryable failures MUST use bounded retry with idempotency. Critical integrity failures MUST preserve prior valid state and generate an audit record.

## 8. Observability

The component MUST emit:

- structured logs;
- correlation and causation IDs;
- duration;
- result status;
- error class;
- relevant object IDs;
- code/schema version;
- model/prompt version when AI participates;
- health or quality metrics relevant to the component.

## 9. Acceptance Criteria

- [ ] Every material relationship has evidence.
- [ ] Meeting does not imply preferred beneficiary or contract.
- [ ] Relationship validity is time-aware.
- [ ] Historical relationship query works.

## 10. Required Tests

- Verify: Every material relationship has evidence.
- Verify: Meeting does not imply preferred beneficiary or contract.
- Verify: Relationship validity is time-aware.
- Verify: Historical relationship query works.

At least one happy-path, one failure-path, one replay/idempotency test where applicable, and one constitutional-boundary test are required.

## 11. Dependencies

Dependencies MUST follow the approved Architecture Package. Provider-specific SDKs MUST remain behind adapters and cross-module writes MUST use owning application interfaces.

## 12. Deferred Items

Any capability not required for the V1 vertical slice MAY be deferred if doing so does not break the canonical contracts, audit lineage, risk controls, or future institutional path.

## 13. Definition of Done

Implementation is complete only when all P0 acceptance criteria have passing evidence, required tests are linked, operational telemetry exists, documentation is updated, and the Engineering Log records the verified result.
