# Superbatch 17 governed live projection publisher

Status: source, fixed binding, adapter, snapshot, and runnable command contracts implemented; persistent publisher not installed or activated.

The operational binding and service package is specified in `SUPERBATCH_17_OPERATIONAL_BINDINGS.md`.

## Boundary

The publisher is a third, independent layer between naturally persisted operational evidence and the existing
15-second browser reader. Browser polling has no route to publisher evaluation, scanners, providers, Keychain,
enrichment, case promotion, paper activity, service repair, or execution. The source-controlled evaluation cadence is
60 seconds, but no scheduler or service is installed by this batch.

Every input uses a fixed source identifier, schema, artifact identity, generated/effective timestamps, immutable
SHA-256, freshness policy, required/optional classification, top-level payload allowlist, and fixed failure behavior.
Registered readers accept only source-controlled filenames below an owner-only root. Unsafe modes, ownership,
symlinks, special files, oversize data, unknown fields, future times, hash mismatches, private 9I, credentials, provider
bodies, raw logs, prompts, model output, private paths, and historical substitution fail closed.

## Publication decisions

Publication occurs only for an initial authentic state, semantic source-hash change, session transition, freshness
boundary, authority/safety change, or sanitized failure replacement. All approved source hashes form one deterministic
semantic hash. Identical input reuses the existing projection timestamp and causes no rewrite or sequence increment.
Changed input uses canonical ASCII JSON, the existing exact-file SHA-256 manifest, monotonic sequence, owner-only
atomic writes, fsync, and rename. Publication time never refreshes source or effective evidence time.

Weekend, holiday, and pre-market views preserve authentic evidence as stale and never claim a new cycle. Regular
session candidates require a complete radar cycle plus exact immutable lineage and are capped at five. Post-market 9H,
9I, and 9J states are observed only after their own natural persistence; the publisher never triggers them. Stale,
failed, missing, or mismatched lineage removes candidate identities. Professional-only evidence remains non-actionable,
and every research lane and sleeve remains separate from operational paper positions.

## Proposed activation package — do not execute without separate approval

- Label: `com.iios.expansion-wing-projection-publisher`
- Module: `expansion_wing.projection_publisher`
- Root: the existing fixed owner-only `EXPANSION_WING_MULTI_ASSET_PROJECTION` root
- Cadence: one bounded evaluation every 60 seconds
- Concurrency: one owner-only nonblocking lock; no child process and no overlapping evaluation
- Recovery: validate exact root inventory, projection and manifest; recover the current sequence without reset
- Logs: bounded fixed categories only, with no source values, paths, exceptions, or evidence
- Stop: graceful termination between evaluations; never interrupt an atomic publication
- Rollback: stop only this proposed publisher, restore its reviewed configuration, retain the last authentic projection
- Reader interaction: none beyond atomic files already consumed by the independent 15-second reader
- Control routes: none; the browser cannot invoke, schedule, or configure the publisher

### Tuesday acceptance

Pre-market must show publisher health, reader active, `PRE_MARKET`, prior evidence stale, and all authority false. After
the first natural scanner cycle persists, one evaluation may increment sequence exactly once and expose either an
authentic empty conveyor or at most five lineage-bound identities. Repeated observations cost and write zero. Changed
inputs publish once. Post-close checks observe completed 9H, natural 9I consumption, 9J advancement, paper truth, and
authority locks without triggering or repairing any source system.

Before activation, review the fixed operational source paths and modes, create rollback evidence, validate a full
Tuesday fixture rehearsal, prove single-flight behavior, approve a bounded logging location, and separately authorize
installation. Provider, Keychain, broker, ledger, paper-order, and live-execution authority remain false.
