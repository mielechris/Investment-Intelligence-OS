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
ledger. The active-release record binds the release ID, Git commit, durable release root, ledger path, immutable release
manifest hash, and a canonical `ledger_path_contract_hash`.

Production deployment therefore requires:

1. an immutable release manifest containing the reviewed supervisor and publisher plist hashes and ledger-path
   contract;
2. an owner-only active-release record using `iios-active-immutable-release-v2`;
3. supervisor and publisher LaunchAgents with identical `IIOS_DB_PATH` values;
4. a fresh projection produced by the production publisher from the authenticated selected executor state; and
5. a supervisor heartbeat produced from those same installed artifacts and persistent roots.

Tests may substitute isolated roots and process probes, but they must not assign, rewrite, or repair projection
generation fields. Shadow acceptance observes projection output produced by `GovernedProjectionPublisher` through the
same release-bound publication path used in production.
