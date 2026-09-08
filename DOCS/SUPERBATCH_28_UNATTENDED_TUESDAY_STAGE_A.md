# Superbatch 28 — Unattended Tuesday Stage A

## Superbatch 28E exact operational binding

The strict operational policy is `iios-unattended-market-session-policy-v2`.
It reads the installed source commit from a fixed owner-only installation
manifest and requires it to equal the commit named by the owner. Browser,
environment, URL, port, and working-directory inference are not trusted. A v1
policy remains rejection/rollback material and is never upgraded implicitly.

The policy separately records an authorized allowance of 50 credits, a Stage A
maximum of 100, initially released credits of zero, and a daily ceiling of 200.
The scheduled release is exactly 50 and cannot expand automatically. Close and
emergency stop return unused allowance to zero.

The supervisor validates the fixed owner-only Financial Datasets readiness
contract before readiness: 50 unique supported identities, zero blocked or
duplicate identities, exact and worst-case cost 50, the reviewed endpoint
allowlist, and the fixed request-plan identity. Missing, changed, expired, or
ambiguous material yields `OPERATIONAL_COST_BINDING_UNAVAILABLE` before any
provider request or allowance release.

## Superbatch 28F authenticated browser projection

Museum status is derived from a fixed-path coherent reader over the installation
manifest, policy, state, and last-known-valid state. It reads and validates the
complete generation twice, retries boundedly when bytes change, and keys the
preview cache by byte identity rather than timestamps. Valid absence projects
`POLICY_NOT_INSTALLED`; a valid installation projects
`AUTHENTIC_OPERATIONAL_POLICY_STATE`; partial, unsafe, or contradictory state is
`UNAVAILABLE`. Rollback to absence is accepted immediately and never inherits a
prior installed-success cache entry. Only sanitized sequence, read time, and
provenance reach the browser.

Released-credit projection is phase-aware: running and partial require exactly
the authorized 50-credit allowance; every disabled, preflight, ready, failed,
locked, stopped, closed, and absent phase requires zero. Invalid combinations
project `UNAVAILABLE` / `FAILED CLOSED` with operator review required and are
never presented as clean policy absence.

This checkpoint commissions source and isolated rehearsal contracts only. The
operational one-day policy and its session state remain absent. The separately reviewed unattended supervisor may be installed in an idle, disabled state; it owns a distinct lock and performs no scheduled work until the one-day policy exists.
until separately checkpointed and authorized.

## Authority boundary

The operational policy schema is `iios-unattended-market-session-policy-v2`; v1
is retained only for strict rejection and rollback compatibility. Its first use is
fixed to Tuesday, September 8, 2026 in `America/Los_Angeles`, is non-recurring,
immutable, canonically hashed, and bound to controller v2, the approved commit,
the ten instruments, the approved endpoint set, and the deterministic 50-item
Stage A request plan. Owner authorization is UTC-only and valid for 0 through
1800 seconds inclusive. Validation precedes state reads, lock acquisition,
writes, service changes, credentials, and providers.

The browser is read-only. It cannot install policy, release credits, invoke the
supervisor, stop the system, contact a provider, access credentials, publish,
promote, trade, write a ledger, or control another service. Stage B and C remain
locked. Automatic retry, reload, budget expansion, and recurring authorization
are prohibited.

## Schedule and recovery

| Local time | Gate |
|---|---|
| 05:55 | Restore and validate exact disabled state |
| 06:00 | Mandatory preflight |
| 06:20 | One deterministic readiness decision |
| 06:30 | Stage A may begin only after every gate passes |
| 09:30 | Bounded intraday observations |
| 12:55 | Closing readiness |
| 13:00 | Closing observation and lock |

Missed observations are never backfilled or burst. A restart recovers completed
request identities and treats confirmed and ambiguous outcomes as already spent.
After the cutoff, execution is partial or failed closed. Emergency closure locks
Stage A, releases zero further allowance, preserves evidence/accounting, and is
idempotent across restart.

## Credits and requests

The system ceiling is 200, but this one-day policy may release only Stage A up to
100. The initial plan contains 50 immutable identities: five windows for each of
MU, SPY, XLK, VNQ, TLT, GLD, UUP, IBIT, PFF, and BIL. Identity binds session,
instrument, endpoint, category, window, provider-contract version, and policy.
Only MU uses company facts; other pilots use an applicable instrument-profile
contract. Unknown endpoint cost blocks before release and before provider access.
Ambiguous outcomes are charged conservatively; cached repeats cost zero.

All 24 rooms participate: 10 pilots, 4 listed-equity source-readiness rooms, and
10 structural rooms. Operational trading rooms remain zero.

## Commands (not installed by this checkpoint)

The fixed-path local module exposes only:

```text
python -m expansion_wing.unattended_tuesday_service --install-one-day-policy \
  --owner-authorization <opaque-owner-authorization> \
  --approval-timestamp <UTC-timestamp>
python -m expansion_wing.unattended_tuesday_service --validate-policy
python -m expansion_wing.unattended_tuesday_service --supervisor
python -m expansion_wing.unattended_tuesday_service --emergency-stop
python -m expansion_wing.unattended_tuesday_service --remove-policy-with-rollback
python -m expansion_wing.unattended_tuesday_service --restore-policy-from-rollback
```

There is no `run now`, browser, arbitrary operational root, activation, Stage B,
or Stage C command. The fixed-path removal command first creates and validates an
owner-only rollback inventory; restoration refuses a populated or ambiguous target.
Executing either remains separately authorized. The emergency stop preserves
receipts and accounting, sets allowance to zero, and survives restart.

## Installation and rollback gate

### Verified unattended-supervisor installer

Superbatch 28H adds `expansion_wing.unattended_supervisor_installer`. Its strict
`iios-unattended-supervisor-installation-v1` manifest binds a reviewed source
commit to a complete sorted fixed artifact inventory. Every entry records only a
relative path, regular-file type, byte size, mode, and SHA-256. The manifest also
binds the fixed service label, state-root identity, module entrypoint, plist
identity, installer version, immutable flag, canonical inventory identity, UTC
installation time, and canonical manifest content hash. Unknown fields,
noncanonical paths, traversal, duplicates, missing or extra files, symlinks,
special files, oversized files, mode/size/hash disagreement, future timestamps,
and source-commit disagreement fail closed.

Operational mode has no caller-selectable destination. It requires an explicit
reviewed-mode flag, a clean synchronized repository, and the expected commit.
Candidate roots are accepted only by the isolated Python test API. Browser,
activation, provider, credential-value, paper, broker, ledger, and execution
arguments are absent or rejected. Candidate hashes are always computed from the
bytes being installed; changing only an old manifest's commit is not a valid
reconciliation.

The non-spending readiness boundary validates the installed manifest/inventory,
one launchd-owned supervisor and exclusive lock, policy absence, controller and
authentic Monday receipt, cost/request-plan/allowance binding, metadata-only
credential readiness, calendar, paper boundary, authority lock, and zero provider
activity. Only that complete state returns
`READY_FOR_OWNER_POLICY_AUTHORIZATION`. It cannot install policy, release credit,
retrieve a credential, contact a provider, or mutate controller, paper, ledger,
projection, candidates, or observations.

Rollback packages are owner-only, inventory-bound, and byte-exact. Restoration
must reject arbitrary destinations, validate the recorded presence/absence state,
stop only the unattended label, wait for label/PID/lock clearance, restore the
complete prior inventory and manifest, bootstrap once, and validate the restored
state. The September 8 policy remains a separate fresh owner authorization.

The canonical supervisor lock filename is owned by
`unattended_tuesday_service.SUPERVISOR_LOCK_NAME` and imported by the installer;
it is never duplicated or derived from input. The resolved path must remain
directly inside the fixed owner-only supervisor root. Missing, held, stale
unlocked, symlinked, malformed, wrong-mode, wrong-owner, and ambiguous states are
classified before teardown proceeds. Changed Python modules must also pass the
installed static undefined-name (`F821`) gate before checkpointing.

The Museum consumes a separate browser-safe supervisor installation projection.
It coherently rereads the fixed strict supervisor manifest, validates every
referenced artifact with the installer validator, validates the fixed Museum
installation identity, and samples launchd/lock/listener/child state. Only two
valid manifests bound to the same commit produce `commit_binding: MATCH`.
Different valid commits produce `MISMATCH`; missing, partial, unsafe, tampered, or
incoherent state produces `UNAVAILABLE`, never clean absence. Browser output is
limited to scalar validity, ownership, counts, bounded generation identity, read
time, and readiness; paths and raw hashes remain server-private.

Before future installation: checkpoint this source; create an owner-only rollback
package; validate actual clock/calendar; validate the authentic Monday receipt;
verify provider costs without charge; prove the credential boundary separately;
render and review the fixed LaunchAgent; and obtain a fresh one-day owner
authorization. On failure, stop only the new supervisor, restore the byte-exact
pre-policy inventory, and leave controller, Museum, paper, projection, provider,
broker, and ledger state unchanged.
