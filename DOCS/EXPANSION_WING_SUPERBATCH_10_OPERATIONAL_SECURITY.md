# Superbatch 10: Operational Security Adapters and Authenticated Review

Status: fixture-first contracts, disabled by default. Implementation cost: **$0**. No package, service, scanner,
Keychain record, operational key, credential or external request was installed, created or accessed.

## Cryptography assessment

The current Python 3.14 environment has none of `cryptography`, PyCryptodome, or PyNaCl installed. The operational
AEAD status is therefore `NOT_AVAILABLE`. The existing Superbatch 9 cipher remains fixture-only and is rejected by
the operational adapter because `operationally_approved=false`.

Proposed dependency, subject to a separate supply-chain and installation review:

```text
cryptography==50.0.1
```

PyPI identifies 50.0.1 as the maintained August 25, 2026 release with Python 3.14 support. Activation must pin the
approved macOS wheel by SHA-256 in a lock file after architecture verification; this batch intentionally does not
download a wheel or guess its platform-specific digest.

The adapter uses the library's `AESGCM` recipe only, with 32-byte keys, 12-byte random nonces, algorithm identifier
`AES-256-GCM`, authenticated versioned metadata, 25 MB plaintext bounds and ciphertext/envelope bounds. It tracks
nonces per adapter instance, rejects reuse, rejects unknown fields and downgrade identifiers, and maps library
decryption failures to a fixed authentication error. A NIST AES-256-GCM known-answer vector is encoded in the
backend conformance harness. Because the dependency is absent, the real backend known-answer execution remains an
activation gate rather than a claimed pass.

## Keychain and recovery design

The Keychain adapter receives a mocked command runner. Creation supplies the 32-byte secret only through protected
stdin; key material is never placed in argv, environment, logs, browser data or repository files. Retrieval accepts
exactly one 32-byte result. Duplicate, missing, inaccessible and ambiguous records fail closed. Rotation verifies
the old key and recovery state before staging a distinct new record. Deletion requires explicit human authorization.

Operational rollout requires a dedicated service name/access group, owner-only ACL, non-interactive access review,
backup recovery ceremony, dual-control rotation and deletion, audit linkage and lost-key acceptance. Lost keys make
the corresponding archive unavailable; they never trigger a fallback cipher, blank key or destructive reset.

## Authentication and service boundary

An owner-admin registry provisions least-privilege rights, transcript, claim, Judgment and Pattern reviewers.
Signed sessions expire after a bounded TTL. Decisions require server-authenticated identity, role authorization,
single-use CSRF values, idempotency keys, replay rejection, 64 KB request limits and ten accepted requests per minute.
Submitter and approver separation is required where applicable. Browser-supplied reviewer names are not part of the
request schema and cannot establish identity.

The separate review-service contract binds only to `127.0.0.1`, defaults disabled, and requires both authentication
and operational-security readiness. Its sole proposed route is `/review/decision`; only exact-schema POST requests
are accepted. It has no ledger, broker, trade, threshold or execution route. It was not installed or started, and no
mutation endpoint was added to the persistent GET/HEAD-only preview.

## Scanner comparison

| Candidate | Strength | Required gate | Status |
|---|---|---|---|
| ClamAV/clamd | Full antivirus engine with maintained signature database and daemon/one-shot interfaces | package provenance, signature updates, isolation, timeout and resource tests | `NOT_CONFIGURED` |
| YARA | Transparent rule-based classification and bounded scan APIs | approved rules, provenance, false-positive review; not sufficient alone as antivirus | `NOT_CONFIGURED` |
| macOS XProtect | Platform-integrated malware defenses | no reviewed supported per-file verdict API for this service | `NOT_AVAILABLE` as adapter |

Every adapter must return name, version, signature age, elapsed time, file size and one fixed result. Only exact
`CLEAN`, current signatures, bounded time and bounded size may pass. Unavailable, stale, timeout, error, ambiguous
or malware results reject quarantine promotion. No scanner was installed or invoked.

## Backup recovery

Encrypted backup manifests require complete record sets, exact hashes, owner-only permissions and audit linkage.
Interrupted writes must preserve the prior complete generation. Restore fails closed for a missing key, missing
record, hash mismatch or incomplete manifest. Recovery-key custody is defined as separate dual-controlled custody;
no recovery secret was generated.

## Browser-safe readiness

Only these scalar states are projected: operational AEAD, Keychain, reviewer authentication, malware scanner,
backup recovery, SEC configuration and review service. Values are limited to `NOT_CONFIGURED`,
`AVAILABLE_FOR_REVIEW`, `READY`, `ERROR`, `DISABLED` and `NOT_AVAILABLE`. Secrets, identities, paths, ciphertext,
documents and security internals are forbidden.

## Remaining activation gates

- approve and hash-pin the `cryptography` wheel, then run the real AES-GCM known-answer suite;
- independent cryptographic/envelope and nonce-persistence review;
- Keychain ACL, recovery custody, lost-key drill and rotation acceptance;
- authenticated identity provider/session-secret custody and append-only audit persistence;
- review-service threat model, port assignment, TLS/local-auth decision and bounded runtime acceptance;
- scanner selection, installation approval, signature-update policy and harmless-file acceptance;
- encrypted backup restore drill and permission audit;
- explicit SEC contact configuration and separate mocked-to-live review;
- separately reviewed preview rebuild and rollback.
