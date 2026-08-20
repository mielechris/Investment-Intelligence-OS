# Data Catalog Acceptance Checklist

## Core

- [ ] Stable opaque IDs defined.
- [ ] Schema versions defined.
- [ ] Common metadata defined.
- [ ] Null semantics defined.
- [ ] Money, units, confidence, and timezone rules defined.

## Point-in-Time

- [ ] Publication, effective, market-available, observed, and system time defined.
- [ ] Disclosure lag represented.
- [ ] Revision/vintage behavior represented.
- [ ] Trading-calendar behavior represented.

## Provenance

- [ ] Source and rights objects defined.
- [ ] Raw record defined.
- [ ] Parse and normalization defined.
- [ ] Quarantine defined.
- [ ] Content hashing defined.

## Knowledge

- [ ] Canonical event defined.
- [ ] Entity and identifier defined.
- [ ] Relationships defined.
- [ ] World-state snapshot defined.
- [ ] Policy lifecycle and regime state defined.

## Markets

- [ ] Instrument defined.
- [ ] Market calendar defined.
- [ ] Derivative fields defined.
- [ ] Bars, quotes, and generic observations defined.

## Evidence and Reasoning

- [ ] Evidence and claims defined.
- [ ] Support/contradiction defined.
- [ ] Causal and counter-chain defined.
- [ ] Hypothesis/thesis defined.
- [ ] Invalidations and falsifiers represented.

## AI and Decisions

- [ ] Agent/model/prompt records defined.
- [ ] Agent runs defined.
- [ ] Committee and dissent defined.
- [ ] Committee decision defined.

## Portfolio and Risk

- [ ] Portfolio/account/positions defined.
- [ ] Risk policy/assessment/decision defined.
- [ ] Order intent/order/fill defined.
- [ ] Accounting and reconciliation objects defined.

## Research and Learning

- [ ] Dataset/feature/strategy defined.
- [ ] Research run/result defined.
- [ ] Journal/postmortem/belief update defined.

## Platform

- [ ] Workflow/jobs/outbox/inbox defined.
- [ ] Audit/incidents/releases defined.
- [ ] Database ownership map defined.
- [ ] Constraints/indexing intent defined.
- [ ] Retention defined.
- [ ] Migration rules defined.

## Final

- [ ] Package placed at `docs/04_data_catalog/`.
- [ ] Catalog matches Packages 01–03.
