# Superbatch 27R — operational v2 controller foundation

Status: `SOURCE CONTRACT / OPERATIONAL MIGRATION SEPARATELY COMPLETED / NOT ACTIVATED`.

The source batch added the production-compatible
`iios-tuesday-controller-state-v2` contract. Operational migration was a
separate rollback-backed procedure and does not activate the controller.

## Compatibility and migration

The state store accepts strict v1 and strict v2 records. Startup validates the
existing schema and never migrates implicitly. A valid v2 record is recovered as
v2 after clean shutdown or restart and is never silently replaced with v1.

The explicit one-way migrator accepts only a valid v1 state paired with its valid
installation manifest. It preserves installation identity, phase, complete phase
history, request identities, confirmed accounting and conservatively classifies
the difference between legacy requests and confirmed credits as ambiguous. The
legacy closed-holiday classification becomes an immutable compatibility receipt
using the legacy state timestamp and schema; it is not represented as a new
operational rehearsal.

Migration increments sequence, installs the 200-credit hard ceiling, creates the
deterministic 50-identity Stage A draft, locks Stage A/B/C at 100/50/50, and
releases zero credits. It leaves activation and every authority false. Before
atomic replacement it writes an owner-only last-known-valid record. Files are
fsynced and the containing directory is fsynced. Repeat migration fails closed.

## Supervisor and recovery

The disabled supervisor remains an offline, single-lock process with no listener
or children. It rejects activation and browser invocation. It validates v1 or v2
before use, writes no implicit migration, and preserves the current schema across
restart. A malformed current file can use only a separately validated
last-known-valid record; the browser receives a sanitized failure state when no
valid record is available.

Operational migration must first capture byte-identical v1 state, installation,
plist and bounded logs, rehearse restoration in isolation, stop only the exact
controller, prove its lock is clear, run the explicit migrator once, and bootstrap
once. Any mandatory failure restores the byte-identical v1 package.

## Browser boundary

The v2 browser contract contains only installed/running/activated status, schema,
phase, integrity, daily and released totals, bounded Stage A/B/C summaries,
aggregate request/credit counts, authority lock, migration/recovery category,
legacy rehearsal classification, sanitized timestamps and fixed errors. It omits
request identities, installation identity, hashes, paths, credentials, selectors,
provider bodies, evidence and mutation controls.

Schema version and presentation provenance are independent. The compositor adds
exactly one server-issued scalar: `controller_status_provenance`. Its only
accepted available values are `AUTHENTIC_OPERATIONAL_STATE` and
`SYNTHETIC_FIXTURE_NON_LIVE`; missing, unknown, contradictory or explicitly
`UNAVAILABLE` provenance produces `CONTROLLER STATUS UNAVAILABLE`.

An operationally configured reader may present valid v1 or v2 state as authentic.
An explicitly fixture-isolated reader may present valid v1 or v2 state only as
synthetic. Browser code must never infer provenance from schema, port, URL, build
mode, phase, installation status or credit values. Authentic v2 is labeled
`AUTHENTIC CONTROLLER STATUS`, `OPERATIONAL V2 · DISABLED`, and
`MIGRATION COMPLETED · CONTROLLER NOT ACTIVATED`. Synthetic v2 remains prominently
marked `SYNTHETIC_FIXTURE_NON_LIVE` and describes migration only as simulated or
rehearsed. Neither presentation adds activation, mutation or provider controls.

## Canonical unified build input

The permanent Museum candidate uses the source-controlled unified endpoint
default. Build with the Expansion Wing application, unified Living Factory,
live-read-only and Backend-recovery gates enabled, and do not redundantly set
`VITE_EXPANSION_WING_READONLY_ENDPOINT`. In unified mode the reviewed default
resolves to `/expansion-wing/snapshot`. Two clean builds must have identical
inventories and byte hashes before installation.
