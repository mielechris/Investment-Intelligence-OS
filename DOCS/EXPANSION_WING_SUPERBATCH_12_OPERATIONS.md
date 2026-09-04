# Superbatch 12 operational manifests

Status: source-only integration. The installed preview, security environment, Keychain item, encrypted archive,
canary and owner record are protected and were not modified. Acquisition and the review portal remain disabled.

## Browser-safe knowledge projection

The preview may read only the bounded `security.json` scalar manifest and filesystem metadata for exact archive
layers and records. It never opens `.enc` files, invokes Keychain, decrypts content or emits identities, paths,
audit events, source text, transcripts, claims, sessions or evidence. Counts and fixed categories are the entire
browser boundary. Missing, malformed, incorrectly owned, permissive or symlinked inputs fail closed to
`UNAVAILABLE`.

## Preview rebuild and installation proposal

1. Require the reviewed commit, clean worktree, healthy Backend 8002 and unchanged protected processes.
2. Build with `VITE_EXPANSION_WING_APP=1`, `VITE_EXPANSION_WING_LIVE_READONLY=1`,
   `VITE_BACKEND_RECOVERY_GREEN=1`, and endpoint `/snapshot`; do not set the fixture flag.
3. Produce the build in a mode-0700 staging directory and verify hashes, room identity and absence of private data.
4. Generate a candidate plist that preserves label `com.iios.expansion-wing-preview`, loopback port 5177,
   GET/HEAD-only behavior and existing source arguments, adding the exact paired `--security-root` and
   `--archive-root` arguments. Validate without loading it.
5. During a separately approved safe-idle window, capture the current plist, static-root hash, PID/start time and
   rollback command; atomically replace only the preview static files and plist, then restart only the preview.
6. Require `/health`, `/snapshot`, method-405, one-listener, one-polling-owner and ten-minute resource acceptance.

## Review portal installation proposal

The portal is a separate owner-authenticated loopback service and is not part of preview 5177. At installation,
select a unique port only after an exact listener and bind preflight. The candidate port 5197 is illustrative, not
reserved. Install only after independent threat-model and service review. Routes are limited to rights,
transcript, claim, contradiction, Judgment and Pattern review. Requests require signed unexpired sessions,
single-use CSRF, idempotency, replay protection, role authorization, a 64 KB ceiling, audit linking and rate
limits. No ledger, broker, trade, threshold, provider, credential, service-control or deployment route exists.

## Security-state preservation

- Never recreate, rotate, print, export or browser-project the archive key.
- Never open encrypted records while composing browser state; inspect only ownership, mode, type and count.
- Require UID 501, directories 0700, records/manifests 0600 and no symlinks.
- Stop on `INVALID_KEYCHAIN_QUERY`; absence may be recognized only as the exact not-found category.
- Keep the review portal disabled unless a later installation approval names the commit, port and rollback.

## Backup verification

Use a fresh authenticated process in the GUI domain. Retrieve the key without output, verify the encrypted backup
manifest, require the complete named record set and exact ciphertext hashes, decrypt into a mode-0700 temporary
directory, verify plaintext hashes internally, then remove only that temporary directory. Never print plaintext,
keys, identities or audit content. A partial set, bad ownership, bad mode, tamper, wrong key or query-context error
fails closed.

## Full rollback

Before any future preview or portal installation, preserve the prior plist, build hash, commit, PID and start time.
Rollback only the newly installed preview/portal artifact and restore the captured preview build/plist. Do not
delete or rotate the protected Keychain item, security environment, archive, canary or owner record for a UI or
portal rollout failure. Security-state removal is a separate destructive ceremony governed by its existing exact
rollback manifest. Never touch Backend 8002, Living Wall, Factory Watch, 9H, 9I, 9J or paper ledgers.

## Daily owner workflow

1. Confirm preview health and fixed false authority fields.
2. Review rights and contact-policy queues; acquisition remains disabled until both are approved.
3. Review transcript corrections and consent before any claim extraction.
4. Review duplicate and contradiction queues with attributed evidence.
5. Promote Judgment or Pattern items only through their human-gated lifecycle.
6. Verify queue limits, cost ceiling, backup readiness and audit-chain continuity.
7. End with no pending browser session and no change to trading, ledger, threshold or provider authority.
