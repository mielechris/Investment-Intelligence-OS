# Superbatch 15 controlled multi-asset projection

Status: source implemented; bounded owner-only projection acceptance authorized; persistent preview activation remains pending.

## Boundary

The publisher accepts only the existing browser-sanitized IIOS snapshot and emits the strict
`iios-multi-asset-read-only-projection-v1` contract. It never opens a ledger, Keychain, provider response, private 9I
artifact, transcript, prompt, model response, or unrestricted evidence record. Candidate identity is accepted only from
the exact current sanitized 9E lineage projection, is capped at five rows, and requires both the current source-cycle ID
and immutable source hash. Aggregate candidate counts and historical promotions are never substituted for identities.
Failed, missing, or ambiguous lineage publishes `UNAVAILABLE` with no candidate rows.

The fixed root has the source-controlled identifier `EXPANSION_WING_MULTI_ASSET_PROJECTION`. Its physical path is
selected only by trusted server code and is never returned to the browser. The directory is owner-only mode `0700`;
the exact inventory is `rollback-manifest.json`, `multi-asset-projection.json`, and `projection-manifest.json`, each mode
`0600`. Unknown pre-existing entries, symlinks, non-regular files, ownership mismatches, permission mismatches, excess
size, malformed JSON, unknown fields, future timestamps, stale projections, source-cycle mismatch, and either hash
mismatch fail closed.

Freshness is evaluated only after those integrity gates pass. An authentic artifact older than 900 seconds remains
readable through a derived browser-safe `STALE` view: the reader is `ACTIVE`, integrity and hash validation are `VALID`,
the publisher remains `UNAVAILABLE`, and evidence is explicitly not current. The derived view is never persisted. It
clears Candidate Conveyor identities, blocks every lane's research and paper eligibility, suppresses professional
observations, and grants no committee, risk, paper, provider, broker, ledger, or execution authority. Exactly 900
seconds is current; any greater age is stale. Invalid, future-dated, malformed, unsafe, or hash-mismatched artifacts
remain `FAILED_CLOSED`.

Publication uses canonical ASCII JSON, SHA-256, same-directory temporary files, `fsync`, atomic replacement, and a
monotonic sequence. Identical input is idempotent and does not rewrite either artifact. The rollback manifest records
the prior absence before the first projection write. The publisher will not initialize, infer, or reset durable provider
credit accounting; missing approved accounting remains null and `UNAVAILABLE`.

## Truth and authority

Null means unknown and is never rendered as zero. `AVAILABLE_EMPTY` is reserved for an observed empty result. Research
sleeves remain separate from operational paper positions. Professional observations are attributed hypothesis-level
research and cannot promote. Paper NAV and cash must equal the authoritative sanitized $10,000/$10,000 baseline, while
positions, transactions, orders, and fills must each be zero for this activation batch. Provider contact, credential
access, automatic promotion, paper orders, ledger writes, broker connectivity, and live execution remain false.

## Activation proposal

The preview reader is disabled by default. A separately reviewed rebuild keeps the existing fixed arguments and adds
exactly `--enable-multi-asset-projection`; there is no browser-provided path. Before that change, verify the root inventory,
owner, modes, hashes, freshness, paper baseline, protected PIDs, and false-authority baseline. Build the live-read-only
frontend, atomically replace only the reviewed preview web assets, and restart only the Expansion Wing preview under a
separate authorization. Roll back by removing the one activation argument and restoring the prior web asset inventory;
the source evidence and approved projection remain unchanged.

## Owner checklist

1. Verify current factory health, source-cycle identity, paper truth, and all authority locks.
2. Publish only after an exact current sanitized snapshot passes the source contract.
3. Verify projection and manifest modes, exact inventory, hashes, sequence, timestamp, and freshness.
4. Review Candidate Conveyor, all ten lanes, professional observatory, scoreboards, research sleeves, and null states.
5. Treat options, bonds, proxies, stale intraday evidence, and professional-only observations as incomplete or blocked.
6. Disable the reader on any mismatch. Never repair source evidence through the projection root.

No daemon, scheduler, provider, credential operation, broker route, ledger mutation, or execution authority is introduced.
