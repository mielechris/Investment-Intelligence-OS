# Superbatch 3.8D — historical lineage repair

Implementation base: `844a1bdd664a8a982cb28601a915e84a13f3088e`.
An edited checkout is not that commit. No operational acceptance is established
by source tests. A later reviewed implementation commit and complete independent
input pins are required before a new build, package, backend or browser run.

## Evidence scope

The 3.8C release candidate and old sb38d package remain quarantined. The owner
attempt-two directory remains quarantined as a directory, including its four
later WAL/SHM sidecars. Only its six originally pinned files are admitted, by
their exact bytes. The preserved attempt-one root remains historical evidence.
The old 252/252 browser result proves its original fixture scenario only.
No existing root is an output destination or a migration source for acceptance.
Do not rewrite timestamps, manifests, browser contracts, hashes or classifications.

## Immutable chain

Owner receipts → six pinned byte sources → verified new working copies →
normalized historical generation and initial publisher cycle → fresh runtime →
package manifest → backend startup receipt → immutable publisher projection →
fresh Northstar contract → browser artifacts → consolidated acceptance.

The package-generation intent hashes the accepted implementation commit,
independently pinned input specification, frontend source inventory and frontend
output inventory. The initial cycle points to that intent, not the later package
manifest, avoiding a hash cycle. Runtime and package records point backward to
the initial cycle. Publications and browser evidence can then bind the completed
package manifest. Receipt byte hashes and canonical content hashes have distinct
fields; neither is substituted for the other.

`truth_spine_lineage.py` opens preserved snapshots only as byte streams. Admission
checks the source pin, exclusively copies the bytes, verifies the copy, then
checks the source again. Only a new working copy is eligible for SQLite checks
and historical adapters. Database sidecars in working directories confer no
accepted status on similarly named files in preserved directories.

The isolated publisher derives new historical cycles from normalized working
records. It preserves event, observation and publication timestamps, source
classifications and the common owner watermark. New publication health never
claims market freshness. No permanent projection-manifest fallback exists.

The runtime manifest names the actual new root, package-relative interpreter,
source commit, package-generation intent, complete runtime file inventory and
pinned platform dependencies. Root, commit, interpreter and inventory mismatches
fail closed. The package-backed full-session endpoint requires the actual
isolated topology, publisher health and its immutable projection. A request
cannot refresh an old projection timestamp.

The new Playwright configuration is separate from the fixture configuration.
It uses the package backend and prohibits request substitution and outside
requests. Each capture binds the delivered projection and hashed asset bytes.
The geometry functions come from the committed source copied into the fresh
package; the old fixture bootstrap and old browser contract are not executed.
The existing fixture, phase, geometry and authority contracts remain separate.

## Inputs and roots required for future authorization

Both JSON templates are deliberately incomplete and must fail admission. Supply
all missing values through a separately reviewed specification in a fresh root:

- A later accepted implementation commit; never use the base commit for edits.
- Fresh independently pinned frontend builds, their common input hash and the
  first complete provenance file hash.
- Complete auxiliary documents, selected executor state, request plan and every
  referenced receipt, all with path, bytes, mode and independent SHA-256.
- Complete interpreter/toolchain and platform-dependency inventories; no old
  package, runtime template or Application Support substitution.
- All 37 configurations, five permanent artifact pins, retained-evidence,
  runtime and Museum inventories, tree membership, protected process identities
  and protected listener ownership. Omitted pins are a blocking condition.
- A separately pinned browser-tools JSON with `node`, `cache` and `harness`.
  Node uses a file pin. Each tree has an absolute `root` and exhaustive `files`
  entries containing `relative` and `pin`. Include dependencies as well as
  harness scripts. No install or browser download is an implicit fallback.
- One unused isolated port, bounded duration and unique root:
  `/private/tmp/iios-truth-spine-3-acceptance-sb38d-clean-<unique-id>/`.

New subdirectories are `admission`, `working-inputs`, `receipts`, `runtime`,
`release`, `state`, `browser`, `baselines`, `rollback` and `logs`. The baseline
precedes preparation and must match after preparation, before execution and
after cleanup. Mutable service state is confined to the new root; immutable
receipts use exclusive creation and cannot be replaced.

## Validation and limits

### Phase 2.2 SQLite reachability boundary

Phase 2.4 separates `read_strict_ledger(spec, capability)` from legacy
`read_ledger`. Every strict capability carries its frozen run policy, independent
receipt pin and exact role/path bindings; validation works with no ambient
context. Context/process audit remains defense in depth, not the admission
authority. Strict native connections reconcile SQLite's actual database list
against the admitted target and return a verified connection wrapper. Strict
verifiers reject raw or substituted legacy connection results before use.

Each strict open writes a new immutable telemetry receipt. Consolidation compares
the final observed target set with the complete expected capability target set,
including both working copies and the event store, and binds the aggregate
receipt. Missing or extra targets fail closed. Unrelated legacy synthetic test
fixtures need no 3.8D registration and confer no 3.8D acceptance evidence.

The strict boundary covers isolated 3.8D, not unrelated legacy applications.
Preparation activates the process policy before admission. Runner and service
activate it from the pinned v3 topology before topology derivation. Service
launches explicitly include `--strict-lineage`; the clean-root name also rejects
legacy topology. Process policy applies to fresh HTTP worker contexts. A scoped
test policy applies only to individually registered synthetic run roots inside
the exact independently selected source-test root.

| Entry path | Permitted role and connection |
| --- | --- |
| `admit` → `check_working_sqlite` | L7/L8 capabilities → `connect_strict_sqlite`, read-only immutable |
| preparation L8 universe query | exact L8 capability → guarded read-only connection |
| `historical_generation` → strict `read_ledger` | exact L7 or L8 capability → guarded read-only connection |
| topology derivation, `ingest`, `snapshot` → `read_bound_ledger` | independently pinned admission → strict L7/L8 adapter |
| `snapshot` paper projection query | exact L8 capability → guarded read-only connection |
| scheduler `ingest` → `connect_event(write=True)` | RUN_EVENT_STORE; scheduler process policy only |
| backend/publisher snapshot and runner counts → `connect_event` | RUN_EVENT_STORE read-only capability |
| rollback and cleanup | byte operations and process observations; no SQLite open |

The sole strict native open is in `truth_spine_adapters.connect_strict_sqlite`.
Its audit permit is scoped to that exact URI and connect operation. Unguarded
`sqlite3.connect` and `sqlite3.Connection` fail in an active strict process,
including fresh worker contexts. ATTACH/DETACH and extension loading are denied;
temporary tables stay in memory. Source snapshots are never SQLite inputs.

Working capabilities bind the exact canonical path, working-input subtree,
role, read-only immutable mode, device/inode, byte-copy creation, matching
source-before/copy/source-after hashes, independently expected admission byte
hash and run/package-generation identity. Event capabilities instead bind an
exclusive empty-file creation receipt, exact state path/inode and independent
parent package hash. The event database and sidecars cannot alias external or
working files. No location or filename suffix confers admission.

Legacy raw branches in shared `read_ledger`, `connect_event` and `snapshot`
remain for earlier topology modes. Strict mode cannot dispatch through them;
the audit hook also rejects an unexpected direct legacy open. The unrelated
`truth_spine_generations.GenerationStore`, snapshot acquisition/capture and
legacy `_adapt` callers remain migration debt. They are not called by the 3.8D
entry graph, and tests exercise rejection of a legacy GenerationStore open in
the strict process context. This is not a repository-wide SQLite migration or
a sandbox against arbitrary native code executing inside the interpreter.

Noninterference requires independently pinned exact file/tree membership.
Protected process membership is scoped by the pinned executable and working
directory pairs; extra or unresolved matching processes fail. Listener census
covers pinned owners and rejects extra listeners, while per-port inspection
also rejects substituted owners. This does not assert an unchanged inventory
of every unrelated OS process. All intended protected scopes must be pinned.

Browser cleanup uses full process fingerprints and exclusive startup receipts,
rechecks each before TERM and KILL, continues after individual exceptions and
retains cleanup attempts. The Python wrapper has its own independently observed
startup receipt and an exclusive log opened before launch; partial output is
retained on failure. Unknown/reused PIDs are not signaled. Surviving children,
changed listeners, unresolved ownership or any cleanup error prevent GREEN.
Port-clear proof requires two empty listener/TCP observations after cleanup.

Executor closure requires independent pins for every receipt and response
referenced by the selector/state/plan graph. Missing parents, orphan inputs,
cycles, unresolved lifecycles and self-hash-valid wrong parents fail closed.
Unsupported executor lifecycles require review rather than inferred evidence.

Phase 2 permits offline tests only, with synthetic inputs retained under
`/private/tmp/iios-sb38d-source-tests-<unique-id>/`. Never use owner snapshots,
quarantined packages or permanent data as test fixtures. Do not run broad test
commands that include actual socket, lease, service or browser scenarios.

The pure admission, runtime, noninterference, publisher, frontend and contract
tests are source-level proofs. They do not establish a usable platform runtime,
a complete external-input inventory, actual browser behavior, full-day evidence
or permanent production readiness. Preserve every test failure and stop at a
mandatory failure. Consult the retained execution logs for the actual test
results; this document does not turn a proposed check into a completed one.

## Cleanup, rollback and consolidation

Cleanup is bounded to newly launched children whose recorded identity still
matches observation. Never signal a reused PID or an unverified process. Any
unresolved child, listener, cleanup error or preservation mismatch prevents
consolidated GREEN. Preserve failed run roots; do not retry within them.

The rollback proof copies an admitted working database to a new rollback file
and verifies equality. It does not restore, replace or write a permanent ledger.
There is no source reset, evidence removal, installation or service promotion in
this transaction. Deleting any new retained test/run root requires separate
authorization with an exact root inventory and hashes.

Checkpoint authorization and execution authorization are separate. A source
checkpoint requires completed offline checks and independent review. Future
execution requires that checkpoint's accepted commit, all complete pins and
explicit authorization for the fresh operational roots and bounded processes.
