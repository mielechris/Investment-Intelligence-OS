# Superbatch 9: Secure Knowledge Operations and Human Review Console

Status: fixture-first, offline contracts only. Cost: **$0**. The installed preview is not rebuilt or restarted and
must not be described as updated until a separately approved installation.

## Encryption threat model

Protected content includes source evidence, normalized notes, claims, transcripts, backup manifests, reviewer audit
links, and content hashes. Threats include disclosure through repository files, logs or browser output; ciphertext
modification; wrong-key use; partial writes; rollback to stale content; failed rotation; unauthorized deletion; and
partial or corrupted restore.

The versioned envelope authenticates immutable metadata as associated data and verifies both an authentication tag
and plaintext SHA-256 after decryption. Writes use a mode-`0600` temporary file, `fsync`, and same-directory atomic
replacement beneath mode-`0700` directories. Interrupted replacement preserves the prior envelope and removes the
temporary file. Rotation first authenticates with the old key and creates a separate new envelope; failure does not
alter the old bytes.

`MacOSKeychainAdapter` is deliberately `NOT_CONFIGURED` and always fails closed. It neither invokes `security` nor
reads Keychain. Tests use only 32-byte ephemeral keys held in process memory inside temporary test directories.
No key, nonce/plaintext pair, private content, or personal identifier is stored in source control, logs, browser
projections, or documentation.

The included `FIXTURE-HMAC-SHA256-ETM-V1` cipher is explicitly test-only and `operationally_approved=false`. It proves
envelope, tamper, recovery, rotation, and key-provider behavior without adding software. Operational activation
requires a separately reviewed standard AEAD implementation supplied through the same adapter, a Keychain access
control design, migration/rotation runbook, and cryptographic review.

## Quarantine threat model

The staging API accepts bytes plus a basename; it never opens a user-supplied path and never executes content.
It rejects traversal names, unsupported extensions, empty/oversized payloads, excessive duration, executable/archive
magic, embedded executable/archive signatures (polyglots), invalid UTF-8/NUL text, media signatures inconsistent with
the declared extension, and content-address targets that are symlinks. Quarantine directories are `0700`; files are
atomically written as `0600` and named by SHA-256. The malware-scanner adapter exposes only fixed outcomes:
`CLEAN`, `MALWARE_DETECTED`, `NOT_CONFIGURED`, or `ERROR`; every outcome except `CLEAN` rejects storage.

No real Jesse recording or external scanner was used.

## Human review workflow

Offline review cases cover source-rights approval, attribution verification, transcript correction, speaker
attribution, Jesse/professional approval, claim classification, contradiction review, Judgment Foundry promotion,
and Pattern Lab submission. Each decision requires reviewer identity, timestamp, reason, and a 64-character previous
audit hash. The canonical event receives its own immutable SHA-256 link. There is no automatic approval, installed
preview mutation, Judgment write, or Pattern submission.

The browser-safe fixture projection exposes only counts, readiness and encryption state (`NOT_CONFIGURED`, `AVAILABLE`,
or `ERROR`). It never includes paths, keys, documents, transcript bodies, hidden reasoning, private evidence,
recommendations, or profitability.

## Mocked SEC compliance

The SEC contact adapter requires an explicitly approved application name and contact at runtime. No personal contact
is hardcoded. The mocked throttle serializes operations, permits at most one request per second, applies bounded
backoff, and permits at most one retry. HTTP 403 or 429 is terminal `ACCESS_POLICY_REJECTED` and is never retried.
No SEC or external network request occurred in this batch; the prior 403 was not retried.

## Acquisition queue and backups

The bounded in-memory queue requires exact domain approval and approved rights before admission. It records priority,
source type, earliest retrieval time, attempt ceiling, deduplication, backpressure and terminal failure. Its view
always reports `scheduled=false` and `network_execution=false`.

Backup manifests enumerate encrypted records by immutable hash and are themselves sealed as encrypted envelopes.
Restore requires the complete record set and exact hashes. Deletion requires explicit human authorization and leaves
an audit tombstone containing hash/reviewer/time/reason but no deleted private content. Retention expiration is
calculated explicitly and never deletes automatically.

## Activation gates

- approved, audited standard AEAD adapter and cryptographic review;
- Keychain access-group, ACL, retrieval, rotation, backup and disaster-recovery approval;
- malware scanner selection and isolated failure-mode acceptance;
- quarantine retention, secure deletion and disk-capacity policy;
- authenticated reviewer identity and durable append-only audit log;
- approved SEC application/contact configuration and access-policy review;
- separately authorized mocked-to-live transition; no scheduling by default;
- provider privacy, retention, training-use, pricing and accuracy approval;
- separately reviewed preview rebuild and rollback;
- continued false broker, trade, ledger-write, credential and live-execution authority.
