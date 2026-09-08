# Superbatch 28 — Unattended Tuesday Stage A

This checkpoint commissions source and isolated rehearsal contracts only. The
operational one-day policy, its state root, and its LaunchAgent remain absent
until separately checkpointed and authorized.

## Authority boundary

The policy schema is `iios-unattended-market-session-policy-v1`. Its first use is
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

Before future installation: checkpoint this source; create an owner-only rollback
package; validate actual clock/calendar; validate the authentic Monday receipt;
verify provider costs without charge; prove the credential boundary separately;
render and review the fixed LaunchAgent; and obtain a fresh one-day owner
authorization. On failure, stop only the new supervisor, restore the byte-exact
pre-policy inventory, and leave controller, Museum, paper, projection, provider,
broker, and ledger state unchanged.
