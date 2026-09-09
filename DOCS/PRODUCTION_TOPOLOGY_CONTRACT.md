# IIOS production topology contract

The immutable production release uses two independent runtime identities:

- `source_cycle_id` is the radar/source-cycle lineage and must never be reused for executor selection.
- `executor_generation` is the authenticated selected operational-executor generation.

A release-bound projection is valid only when its projection payload and projection manifest carry the same
`executor_generation`, and that value matches both the supervisor heartbeat and the authenticated selected executor
generation. Missing, malformed, stale, or contradictory bindings fail `/health/ready` closed.

The operational SQLite ledger is persistent state, not an immutable release artifact. Its absolute path is supplied by
the reviewed LaunchAgent configuration through `IIOS_DB_PATH`. The path must be identical for the supervisor,
publisher, and backend; must resolve outside the immutable release root; and must identify the owner-only operational
ledger. The active-release record binds the release ID, Git commit, durable release root, dedicated immutable Python
runtime, ledger path, release/runtime manifest hashes, reviewed ledger migration contract, and a canonical
`ledger_path_contract_hash`.

Production deployment therefore requires:

1. an immutable release manifest containing the reviewed supervisor and publisher plist hashes and ledger-path
   contract;
2. an owner-only active-release record using `iios-active-immutable-release-v3`;
3. supervisor and publisher LaunchAgents with identical `IIOS_DB_PATH` values;
4. a fresh projection produced by the production publisher from the authenticated selected executor state; and
5. a supervisor heartbeat produced from those same installed artifacts and persistent roots.

Tests may substitute isolated roots and process probes, but they must not assign, rewrite, or repair projection
generation fields. Shadow acceptance observes projection output produced by `GovernedProjectionPublisher` through the
same release-bound publication path used in production.

## Ledger permission migration

The only reviewed ledger permission transition is `0644` to `0600`. Before `chmod`, deployment validates the exact
absolute path, regular-file type, absence of symlinks and SQLite sidecars, owner/group, device/inode, size,
authenticated SHA-256, and SQLite `quick_check`. It then verifies the same device/inode, size, SHA-256, and database
integrity after changing only the mode. Any discrepancy restores `0644` and fails closed. The rollback disposition may
restore `0644` only after revalidating the recorded identity and content hash.

Permanent promotion evidence records both modes and the migration receipt hash. Shadow acceptance exercises this
transition only against an isolated byte-identical ledger copy; development and packaging never change the operational
ledger.

## Immutable Python runtime

Production services use a dedicated runtime beneath `~/Library/Application Support/IIOS/Runtimes`, never a virtual
environment or interpreter inside a Git checkout. Its manifest binds Python 3.14.7, interpreter bytes, exact installed
dependency inventory, complete file inventory, and unavoidable platform-library dependencies. Runtime files and
directories are sealed non-writable. Symlinks, missing files, version drift, dependency drift, paths escaping the
runtime, and platform dependencies inside a checkout fail closed.

All four production plists use the manifest-bound runtime interpreter and immutable release paths. `PYTHONPATH` and
working directories point only into the immutable release, and the identical external `IIOS_DB_PATH` is supplied to
Backend, Museum, publisher, and supervisor.
