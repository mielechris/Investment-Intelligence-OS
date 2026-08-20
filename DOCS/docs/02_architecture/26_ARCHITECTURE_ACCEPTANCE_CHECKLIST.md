# Investment Intelligence OS
## Architecture Acceptance Checklist — v0.1

---

## Governance

- [ ] Architecture obeys the System Constitution.
- [ ] Paper-only V1 is explicit.
- [ ] Risk veto is explicit.
- [ ] Public or properly licensed information boundary is preserved.
- [ ] No-trade and stand-down are first-class states.
- [ ] Material decisions have ADR placeholders or records.

## Architecture Style

- [ ] Modular-monolith decision is explicit.
- [ ] Module ownership is explicit.
- [ ] Cross-module dependency rules are explicit.
- [ ] Service extraction criteria are explicit.
- [ ] Browser is not a source of authoritative financial state.

## Runtime

- [ ] API, worker, scheduler, and frontend responsibilities are defined.
- [ ] Startup and shutdown behavior are defined.
- [ ] Environment separation is defined.
- [ ] Paper environment cannot load live authority.
- [ ] Deployment and rollback concepts are defined.

## Data

- [ ] PostgreSQL is the transactional system of record.
- [ ] Object storage owns immutable raw and large artifacts.
- [ ] Cache is disposable.
- [ ] Raw data is immutable.
- [ ] Four primary timestamps are represented.
- [ ] Revision and retraction behavior are defined.
- [ ] Data retention and backup are defined.

## Identity

- [ ] Canonical IDs are opaque and immutable.
- [ ] Provider IDs and tickers are mappings, not primary identity.
- [ ] Entity merge and split are audited.
- [ ] Instrument contracts are distinguishable.
- [ ] Theme and causal-cluster identity exists.

## Ingestion

- [ ] Connector, parser, and normalizer are separate.
- [ ] Checkpoints are durable.
- [ ] Deduplication is defined.
- [ ] Rate limits and retries are defined.
- [ ] Quarantine is defined.
- [ ] Source health is defined.
- [ ] LLM-assisted extraction is validated.

## Workflow

- [ ] Durable job ledger is defined.
- [ ] Worker leases are defined.
- [ ] Transactional outbox is defined.
- [ ] Consumer inbox is defined.
- [ ] Idempotency keys are defined.
- [ ] Replay rules are defined.
- [ ] Stand-down propagation is defined.

## Knowledge and Evidence

- [ ] World-state snapshots are immutable.
- [ ] Evidence graph objects are defined.
- [ ] Support and contradiction are represented.
- [ ] Policy lifecycle distinguishes intent and implementation.
- [ ] Regime state is probabilistic.
- [ ] Historical analogs include differences.

## Reasoning

- [ ] Fact, inference, hypothesis, thesis, and decision are separated.
- [ ] Causal chain is structured.
- [ ] Counter-chain is mandatory for promoted theses.
- [ ] Missing information is explicit.
- [ ] Invalidation is explicit.
- [ ] Explainability packet is defined.
- [ ] Confidence is multidimensional.

## Agents and Committee

- [ ] Agent card contract is defined.
- [ ] Model gateway is defined.
- [ ] Tool permissions are allow-listed.
- [ ] Agent output is structured and immutable.
- [ ] Abstention is supported.
- [ ] Prompt injection controls are defined.
- [ ] Committee preserves dissent.
- [ ] Committee cannot place orders.

## Portfolio and Risk

- [ ] Portfolio ledger is authoritative.
- [ ] Risk policy is versioned.
- [ ] Risk is deterministic.
- [ ] Risk veto is enforced.
- [ ] Causal-cluster concentration is represented.
- [ ] Approval expiration is defined.
- [ ] Kill switches are defined.
- [ ] Derivative-specific controls are acknowledged.

## Paper Execution

- [ ] Paper adapter contract is defined.
- [ ] Order lifecycle is defined.
- [ ] Idempotent order intent is defined.
- [ ] Fill assumptions are versioned.
- [ ] Accounting is atomic and reconcilable.
- [ ] Paper/live separation exists beyond the UI.

## Research and Learning

- [ ] Point-in-time dataset manifest is defined.
- [ ] Leakage tests are defined.
- [ ] Baselines are mandatory.
- [ ] Costs and slippage are mandatory.
- [ ] Holdout and walk-forward are defined.
- [ ] Reverse engineering is treated as hypothesis.
- [ ] Promotion ladder is defined.
- [ ] Postmortem distinguishes process from outcome.

## API and Frontend

- [ ] Versioned API is defined.
- [ ] Stable error model is defined.
- [ ] Long-running jobs are asynchronous.
- [ ] Idempotency is supported.
- [ ] Frontend pages and states are defined.
- [ ] Data freshness is visible.
- [ ] Decision lineage is navigable.

## Security

- [ ] Threat model exists.
- [ ] Secrets are externalized.
- [ ] Least privilege is defined.
- [ ] Model data boundary is defined.
- [ ] Dependency security is defined.
- [ ] Incident response is defined.
- [ ] Audit is protected.

## Reliability

- [ ] Structured logs are defined.
- [ ] Metrics are defined.
- [ ] Correlation and tracing are defined.
- [ ] Health levels are defined.
- [ ] Critical alerts are defined.
- [ ] Backup and restore are defined.
- [ ] Operational reconciliation is defined.
- [ ] Safe degradation is defined.

## Testing

- [ ] Unit, property, contract, integration, and end-to-end layers are defined.
- [ ] Golden trace is defined.
- [ ] Failure-path tests are defined.
- [ ] Point-in-time tests are defined.
- [ ] Risk invariants are defined.
- [ ] Accounting tests are defined.
- [ ] Security and recovery tests are defined.

## Delivery

- [ ] Repository structure is defined.
- [ ] Seven-day slice is defined.
- [ ] Deferred decisions are recorded.
- [ ] Architecture documents have version and status.
- [ ] Package can be placed at `docs/02_architecture/`.
