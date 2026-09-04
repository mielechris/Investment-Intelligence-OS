# Tuesday multi-asset readiness runbook

This runbook does not authorize provider contact, Keychain access, process control, operational-ledger writes, paper orders, broker access, or live execution. The projection reader is disabled by default and must be separately reviewed before installation.

## Read-only projection contract

The server-configured reader accepts only `multi-asset-projection.json` beneath its reviewed root; the browser cannot select a path. The versioned projection is capped at 65,536 bytes, rejects unknown fields, uses canonical ASCII JSON and a deterministic SHA-256, and contains only bounded candidate and scalar status records. Missing counts remain `null`; they never become zero. A failed cycle cannot carry candidate identities from an earlier successful cycle. All provider, credential, promotion, order, ledger, broker, and live-execution authority fields are explicitly false.

## Pre-market

1. Observe protected service health, PID, start time, and listener without restarting anything.
2. Require an approved exchange-calendar result. Otherwise display `UNKNOWN`; never infer a holiday.
3. Confirm source, effective, session, and projection timestamps.
4. Confirm the projection reader remains disabled unless its separate activation gate is approved.
5. Display provider and credit status from sanitized accounting only. Missing values remain unavailable.
6. Confirm provider, credential, promotion, order, ledger, broker, and execution authority are false.
7. Begin Tuesday as `PRE_MARKET` or `UNAVAILABLE`; Friday evidence is `STALE`, not current.

## After open

1. Wait for one naturally completed current-session scanner cycle.
2. Require the exact immutable 9E cycle, timestamp match, artifact hash, and candidate lineage.
3. Populate no more than five Candidate Conveyor rows.
4. Run bounded provider enrichment only under separate authorization and durable credit accounting.
5. Treat professional observations as attributed hypotheses with disclosure delay and rights status.
6. Require independent primary evidence and point-in-time historical testing.
7. Display missing evidence, contradictions, correlation, proxy basis, and freshness per lane.
8. Intraday eligibility remains false outside the regular session or when latency/pricing is stale.

## Paper promotion

The required sequence is Skeptic review → primary-source review → committee review → deterministic risk review → human approval → bounded paper proposal. Research sleeves never create an operational paper position. No automatic order generation is allowed.

## Post-close

1. Require complete full-session 9H validation.
2. Observe whether 9I consumed the validation naturally; do not inspect private 9I evidence.
3. Observe whether 9J advanced naturally.
4. Record the outcome state and immutable timestamps.
5. Reconcile the authoritative `$10,000` paper NAV/cash and zero unauthorized activity.
6. Reconfirm every authority flag remains false.

## Failure procedure

Display the fixed sanitized failure category and preserve the last trustworthy timestamp and hash. Do not restart automatically, retry providers, reset credit accounting, substitute historical candidates, infer missing zeros, or weaken specialized options, bond, proxy, or intraday gates.

## Activation gates remaining

Activation requires human review of the isolated visual, a reviewed owner-only projection root, an exact source publisher, freshness policy, approved calendar source, bounded polling proof, rollback manifest, and protected-process acceptance. Provider-enabled lanes additionally require source-specific licensing, retention, cost, and outage approval. Later broker work requires separate authorization, forward validation, reconciliation, kill controls, and security review.
