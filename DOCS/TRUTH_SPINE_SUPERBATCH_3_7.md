# Superbatch 3.7 — bounded installed Northstar historical replay

This is not a market-day run. Permanent services, ledgers, credentials and
provider/model/broker boundaries remain untouched. All operational capabilities
remain false. Retained candidate, specialist, Committee, Risk and outcome records
are replayed as retained evidence, not newly executed research decisions.

## Separate historical contract

`iios-historical-shadow-session-v1` uses the actual UTC capture/publication clock,
has a 300–3600-second lifetime, and reserves its final minute for shutdown.
It has no market-calendar authority, opening observation, catch-up or backfill.
Its active phase is post-close reconciliation and its incident label explicitly
says `HISTORICAL_REPLAY_NOT_FULL_MARKET_DAY`. Original evidence times and
classifications are not rewritten. The normal exchange calendar, market-day
schema, 24-hour maximum authority and source-cycle freshness rules are unchanged.

Only `iios-northstar-installed-shadow-sb37` may use this historical contract.
The market-day runner must reject that root for an exchange session, and the
service must reject a historical session in a market-day root. The same installed
capture, journal, source-cycle, publisher, readiness and process-ownership paths
are used; browser requests cannot create captures or publish projections.

## Packaging procedure

The two exact Northstar build roots are `iios-northstar-sb37-build-a` and
`iios-northstar-sb37-build-b`, beneath the system temporary directory. The existing
source-bound offline builder now accepts these two names explicitly; it does not
accept arbitrary additional Northstar roots or existing directories.
The independent source-build regression keeps its temporary build roots beneath
its disposable checkout's `tests/northstar/artifacts` directory. Only names with
the fixed `iios-frontend-build-unit-` prefix are accepted there; symlinked parents
are rejected. It no longer creates additional top-level temporary build roots.

`scripts/truth_spine_historical_package.py` validates both complete frontend
provenance records, clean committed source, pinned original runtime inventory,
and the committed Python dependency lock. It prints a deterministic prospective
inventory without creating an installation. Installation requires that separately
reviewed candidate content hash via `--candidate-sha256`; no self-selected pin
is supplied automatically. The `--install` switch never starts a process.

The package contains the fixed sixteen-module backend graph, all thirteen
Northstar assets, and a dedicated Python runtime. Checkout-bound activation
scripts and pip are excluded; the new runtime inventory and sanitized CPython
configuration are hash-bound. No dependency installation or network access is
performed. Source is 0400, the interpreter is 0500, directories are owner-only,
and runtime state is separate from immutable artifacts. Unknown inventory,
changed bytes, invalid modes, path escape, caches and symlinks fail closed.

Actual input files must be enumerated and pinned before creation. SQLite
snapshots are individually consistent; no global simultaneity is claimed.
The authority is issued after immutable copying, with real system UTC time,
so preparation cannot silently backdate or consume an expired approval.
The package/root is retained on any post-creation failure.

## Service ownership

Backend startup receipt publication occurs only after the exclusive lease and
successful HTTP bind. Duplicate lease/bind failure grants no process ownership.
Scheduler and publisher receipts likewise require the lease first. The stabilized
OS fingerprint acquisition and independent cleanup contracts remain mandatory.
The backend is also the single static Northstar server; the publisher is the
single projection producer. There is no second same-port frontend listener.

Northstar assets are served from the manifest-pinned installed graph, including
WebP portraits. The frontend reads only `/truth-spine/full-session`. Historical
research readiness is labeled `HISTORICAL_REVIEW_READY`; market readiness stays
503. A current capture never upgrades the age or classification of source data.

## Acceptance status

### SQLite-owned acquisition (3.7C continuation)

Do not gate acquisition on a separate WAL/SHM existence check. Open SQLite with
`mode=ro`, enable and verify `query_only`, verify `database_list`, then `BEGIN`
and perform a schema read to establish the transaction snapshot. `BEGIN` alone
is deferred and is not evidence of a pinned view. Keep this read transaction
open throughout SQLite backup and destination integrity validation, then end it
with rollback and close the handle, including on failure. A later writer commit
or checkpoint must not move the pinned view. Source inode replacement still
fails closed; ordinary advancement is not replacement.

Operational acquisition must run under independently verified OS source-write
denial. SQLite read-only/query-only flags alone do not guarantee zero companion
file creation. If SQLite cannot acquire the view under that denial, report
`SOURCE_SNAPSHOT_NOT_ACQUIRED`, not corruption inferred from disappearing files.
No automatic retry, companion creation, immutable=1 bypass or raw copy is added.
The transaction helper and disposable regressions do not certify a permanent
capture or provide the still-required process-isolation packaging by themselves.

The source-only capture boundary is now explicit in
`truth_spine_sqlite_capture.py`. It creates a hash-bound macOS Seatbelt profile,
launches one pinned Python child, admits it only after a kernel denial query and
process fingerprint, and writes startup/failure receipts in an independent
owner-only evidence root. The profile denies source/WAL/SHM writes, source
metadata/rename/unlink, writes outside the exact destination, networking, Mach
lookup and credential paths while allowing signed runtime reads. The operational
runner passes this launcher into `SessionSupervisor`; a production capture cannot
silently use the direct SQLite reader. Direct helper use remains available to
isolated unit fixtures only. A child failure is retained as a sanitized incident,
and no snapshot publication or authority follows it.

Historical writer attribution remains `ATTRIBUTION_UNPROVEN`, accepted only as
an explicit historical-shadow limitation. Permanent promotion remains blocked.

Source repair and installation acceptance are separate gates. This document is
not evidence that a package was installed, a process started, or browser acceptance
passed. The owner-only machine receipt must record actual results, source and
runtime identities, snapshots, projections, ownership, shutdown and permanent
noninterference before any GREEN or Superbatch 3.8 planning recommendation.

## Owner-operated L7/L8 snapshot kit (3.7E.7)

The source-only kit is `scripts/truth_spine_owner_snapshots.py`. Codex must not
execute it. An owner prepares a separate owner-only JSON configuration from
`config/truth-spine-owner-sources.json.template`, sealing it with the
`iios-truth-spine-contract` canonical JSON rules. Version 3 separates mutable
source binding from immutable snapshot identity. Each of exactly two distinct
regular files is bound to its role (`L7_OPERATIONAL` or `L8_HISTORICAL`),
canonical path, device, inode, owner UID, observed mode and observation UTC.
Prior audit size/SHA/time values are retained only under `prior_observations` as
historical provenance; they are never presented as the current source identity.
Source mode `0644` is disclosed as hardening debt and is not changed by this
batch. Symlinks, special files, credential/keychain paths, placeholders,
checkout/output paths, role swaps and metadata changes fail closed.

`--config-only` is a metadata-only preflight: it reads the config JSON and uses
`lstat` on the two sources, but never reads source bytes, opens SQLite, touches
WAL/SHM files, creates the output root, or accesses credentials. At capture,
path/device/inode/owner/type are revalidated, size and mtime may advance, and
the immutable identity is the completed SQLite-consistent snapshot SHA-256.
The kit has no
browser route. Discovery is bounded to explicitly supplied accepted metadata
files (LaunchAgent/release-manifest references); it does not scan a home
directory, guess filenames or auto-adopt a candidate. An owner must select a
single L8 candidate and provide the exact confirmation below.

The owner runs pinned Python 3.14 with the exact sentence below. The command
requires the fixed output root `/private/tmp/iios-northstar-owner-snapshots-sb37`
to be absent and never overwrites an existing root. Each source is opened by
the reviewed macOS Seatbelt helper (`truth_spine_sqlite_capture.py`) in
`mode=ro`, with `query_only`, an established read transaction, SQLite backup,
integrity and foreign-key checks. Snapshots, manifest and completion receipt are
fsynced, owner-only and hash-bound. Only aggregate table counts, schema hashes
and UTC high-watermarks are recorded; no rows, payloads, credentials or private
paths are printed. Interruptions and validation errors leave sanitized failure
evidence and no success receipt.

Copy/paste template (replace only the owner-created config path):

```bash
cd /path/to/clean/iios-truth-spine-3-src && \
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python \
  scripts/truth_spine_owner_snapshots.py \
  --source-root "$PWD" \
  --config /owner-controlled/iios-owner-ledger-sources.json \
  --expected-commit <POST-CHECKPOINT-COMMIT> \
  --helper-sha256 <POST-CHECKPOINT-HELPER-SHA256> \
  --owner-kit-sha256 <POST-CHECKPOINT-OWNER-KIT-SHA256> \
  --confirm 'I authorize opening these already-adopted L7 and L8 ledgers for read-only capture into the isolated owner snapshot root.'
```

The owner confirmation used to seal the configuration is exactly: `I confirm
these are my canonical IIOS L7 and L8 ledgers. I authorize read-only capture
into the isolated owner snapshot root. I do not authorize source modification.`
After config-only validation prints a sanitized config hash, the owner must
provide the second capture confirmation in the command above. This is a
two-person/owner-controlled boundary: the source kit never chooses an L8 path
and Codex never runs the capture command.

Before running, the owner independently verifies the source commit and helper
SHA-256 pins supplied after the source checkpoint. The helper emits the exact
profile SHA-256 for each output in the sealed capture job and manifest, so the
receipt binds the generated profiles without asking the owner to guess them.
This owner action creates no LaunchAgent,
accesses no provider or Keychain, calls no model/MCP route, writes no operational
ledger, and publishes no projection. A `VERIFIED` result is only a read-only
snapshot receipt for later review, not market-day approval. No independent pinned
L8 configuration is present in this checkout, so the procedure is currently
GO/NO-GO = NO-GO until the owner supplies and validates that configuration.
