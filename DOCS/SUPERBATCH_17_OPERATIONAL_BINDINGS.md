# Superbatch 17K–17P operational publisher bindings

Status: source-only implementation and isolated rehearsal. The publisher LaunchAgent is not installed or active.

## Fixed source inventory

Operational bindings are defined only by `projection_bindings.json`. Runtime code resolves four reviewed logical roots:
`TELEMETRY`, `MARKET_VALIDATION`, `MARKET_VALIDATION_BROWSER`, and `PUBLISHER_SOURCES`. No browser or CLI value can
replace a root or filename. Personal absolute paths are neither source-controlled nor projected.

The existing sanitized factory telemetry supplies factory health, deterministic weekend session status, radar-cycle
status, paper truth, and authority locks. Compact 9H, browser-safe 9I, and browser-safe 9J artifacts supply their own
states. Candidate lineage, professional research, research sleeves, and sanitized provider accounting have fixed
publisher-source filenames but are presently optional and absent. Multi-asset lane evidence also has a fixed absent
source; its required availability envelope exposes all ten lane identities as `UNAVAILABLE`, with null counts and all
eligibility false. This is availability reporting, not invented market evidence.

The market-session adapter recognizes weekends deterministically. On a weekday it reports `UNKNOWN` unless a future
approved session artifact establishes the phase; it never independently asserts an exchange holiday. A failed radar
aggregate exposes no candidate identity. Only the unversioned outer 14G–14K lineage projection containing a versioned
`iios-sanitized-scanner-batch-v1` batch may provide at most five identities.

Each adapter preserves the exact source-byte SHA-256 plus original generated/effective timestamps, uses a versioned
adapter identity, and emits the strict `iios-projection-source-envelope-v1` contract. Missing sources use a stable
absence identity and epoch timestamp so observation cannot make absence appear fresh.

## Snapshot and command behavior

One observation descriptor-reads each unique bound artifact once, even when several logical adapters share it. The
builder validates all thirteen envelopes and commits an owner-only exact inventory with a manifest containing source
hashes, envelope hashes, and adapter versions. Identical semantics cause zero writes. The manifest is committed last,
so an interrupted staging attempt cannot become a consumable snapshot.

The command is `python -m expansion_wing.projection_publisher --operational`. It performs one immediate observation,
then uses a monotonic 60-second minimum loop. `--once` performs one bounded observation and
`--validate-bindings` performs read-only source validation. Operational path overrides and unknown arguments are
rejected. A nonblocking owner-only lock prevents overlap. SIGTERM and SIGINT request graceful stop between observations.
The internal status log is owner-only, size bounded, atomically replaced, and contains fixed categories only.

There is no network, Keychain, scanner, service-repair, broker, ledger, order, or browser-control path.

## Future LaunchAgent specification — not installed

- Label: `com.iios.expansion-wing-projection-publisher`
- Executable: established fixed IIOS Python 3.14 interpreter
- Arguments: `-m expansion_wing.projection_publisher --operational --interval 60`
- Working directory: reviewed repository backend root
- Environment: fixed `PYTHONPATH` only; no inherited provider or trading enablement
- RunAtLoad: true
- KeepAlive: true with fail-closed observation isolation and launchd throttling
- Standard output/error: `/dev/null`; bounded sanitized status is managed by the service
- Lock/status root: fixed owner-only `ExpansionWingPublisher`
- Input root: fixed owner-only `ExpansionWingPublisherInputs`
- Projection root: existing owner-only `ExpansionWingProjection`

Before future installation, validate the exact committed SHA and clean tree, verify each source mode/owner/schema,
create the three owner-only publisher roots, capture the sequence/hash and protected-service baseline, render and lint
the concrete plist, and prove no publisher label/PID/lock exists. Bootstrap once into the authenticated GUI domain.

Rollback boots out only this label, waits for label/PID/lock absence, removes only files identified by its rollback
manifest, and retains the last authentic projection without decreasing sequence. Existing 5177 continues reading that
projection and has no route back to the publisher.
