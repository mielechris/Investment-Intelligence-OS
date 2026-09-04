# Superbatch 11B: Owner-Administrator Authorization

Status: source-only repair. No operational target, Keychain item, dependency, archive or service is created.

## Authorization matrix

| Role | RIGHTS | TRANSCRIPT | CLAIM | JUDGMENT | PATTERN | ADMINISTER_REVIEWERS |
|---|---:|---:|---:|---:|---:|---:|
| OWNER_ADMIN | yes | yes | yes | yes | yes | yes |
| RIGHTS_REVIEWER | yes | no | no | no | no | no |
| TRANSCRIPT_REVIEWER | no | yes | no | no | no | no |
| CLAIM_REVIEWER | no | no | yes | no | no | no |
| JUDGMENT_REVIEWER | no | no | no | yes | no | no |
| PATTERN_REVIEWER | no | no | no | no | yes | no |

The permission model contains no ledger, broker, trading, threshold, provider, service-control or deployment
authority. Owner administration cannot create another owner, mutate the owner itself or assign a role outside the
specialized review-role allowlist. Owner review authority does not bypass domain rights, consent, attribution,
source evidence, transcript approval, Judgment lifecycle or Pattern Lab gates.

## Bootstrap state machine

`EMPTY` → `LOCAL_OWNER_CEREMONY` → `ONE_OWNER / PERMANENTLY_CLOSED`

Bootstrap starts only from an empty registry under a process-local lock. The ceremony requires an exact expected
local identity, matching presented local identity, owner-controlled storage, a matching one-time nonce of at least
32 characters and an explicit non-browser origin. It atomically installs exactly one opaque `OWNER_ADMIN` and
permanently closes bootstrap. A pre-populated registry, retry, browser-origin ceremony, identity mismatch, missing
storage control, duplicate owner or ambiguous multi-owner state fails closed.

## Decision and audit boundary

Every governed or administrative authorization requires a valid signed and unexpired session, active reviewer,
exact action permission, single-use CSRF value, unique idempotency key, bounded request size, per-reviewer rate
limit, reason, ISO timestamp and the exact previous audit hash. Accepted events contain the prior hash and a
deterministic new hash. They expose no session, CSRF value, signing secret, local identity or filesystem path.

Reviewer add, disable and role-change operations are reachable only through authenticated
`ADMINISTER_REVIEWERS`; the registry mutation primitive is private. The separate review service remains disabled,
and reviewer administration is deliberately not exposed as a browser route.

## Activation resumption point

After this source batch is independently reviewed, committed and pushed, secure activation may restart from its
initial absence and protected-state preflight. The prior failed activation was fully rolled back. Package download,
environment creation, operational Keychain creation and archive creation must be repeated from the reviewed exact
commit; none may be reused from the failed attempt.
