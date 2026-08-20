# Implementation Acceptance Checklist

## Repository

- [ ] Root files exist.
- [ ] Git ignore protects secrets/artifacts.
- [ ] Safe env example exists.
- [ ] Backend and frontend bootstrap.

## Environment and Security

- [ ] Typed settings.
- [ ] PAPER guard.
- [ ] Secret provider.
- [ ] Secret scan.
- [ ] Owner identity.
- [ ] Service identity.
- [ ] Rights enforcement.
- [ ] Stand-down state.

## Database

- [ ] PostgreSQL starts.
- [ ] Migrations work.
- [ ] Logical schemas exist.
- [ ] Required extensions exist.
- [ ] Core tables exist.
- [ ] Constraints tested.

## Workflow

- [ ] Jobs durable.
- [ ] Leases recover.
- [ ] Retries bounded.
- [ ] Outbox/inbox works.
- [ ] Scheduler idempotent.
- [ ] Replay safe.

## Ingestion

- [ ] Source registry.
- [ ] Object store.
- [ ] Raw capture.
- [ ] Parser registry.
- [ ] Normalizer registry.
- [ ] Dedup/revision.
- [ ] Health.
- [ ] Quarantine.
- [ ] Three source domains.
- [ ] Market-data adapter.

## Knowledge and Reasoning

- [ ] Entity resolution.
- [ ] Relationships.
- [ ] Policy lifecycle.
- [ ] World snapshot.
- [ ] Evidence.
- [ ] Claims.
- [ ] Causal chain.
- [ ] Counter-chain.
- [ ] Hypothesis.
- [ ] Thesis.
- [ ] Hard gates.
- [ ] Explainability.

## AI

- [ ] Model Gateway.
- [ ] Model registry.
- [ ] Prompt registry.
- [ ] Governed retrieval.
- [ ] Tool allow-list.
- [ ] Agent executor.
- [ ] Prompt-injection defense.
- [ ] Policy Analyst.
- [ ] Macro Analyst.
- [ ] Skeptic.
- [ ] Committee.

## Portfolio / Risk / Paper

- [ ] Paper account.
- [ ] Portfolio snapshot.
- [ ] Causal clusters.
- [ ] Risk policy.
- [ ] Risk assessment.
- [ ] Risk decision.
- [ ] Order intent.
- [ ] Paper adapter.
- [ ] Fill model.
- [ ] Accounting.
- [ ] Reconciliation.
- [ ] Kill switch.

## Research and Learning

- [ ] Dataset manifest.
- [ ] Point-in-time builder.
- [ ] Baselines.
- [ ] Event study.
- [ ] Backtest.
- [ ] Walk-forward.
- [ ] Sensitivity.
- [ ] Regime report.
- [ ] Postmortem.
- [ ] Calibration.

## API and Frontend

- [ ] API health.
- [ ] Auth.
- [ ] Safe errors.
- [ ] Core query endpoints.
- [ ] Typed frontend client.
- [ ] Today page.
- [ ] Decision detail.
- [ ] Portfolio/risk page.
- [ ] System health page.

## Operations

- [ ] Structured logs.
- [ ] Health aggregation.
- [ ] Metrics.
- [ ] Alerts.
- [ ] Backup.
- [ ] Restore.
- [ ] Daily scheduler.

## Quality

- [ ] Backend lint/type/test.
- [ ] Frontend lint/type/build.
- [ ] PostgreSQL integration tests.
- [ ] Architecture boundary tests.
- [ ] Constitutional tests.
- [ ] Golden trace.
- [ ] Failure golden traces.
- [ ] CI.
- [ ] Release manifest.
- [ ] V0.1 release checklist.

## Final

- [ ] All P0 blockers closed.
- [ ] PAPER mode only.
- [ ] Golden trace reconstructable.
- [ ] Backup/restore proven.
- [ ] Risk veto proven.
- [ ] No critical security issue.
