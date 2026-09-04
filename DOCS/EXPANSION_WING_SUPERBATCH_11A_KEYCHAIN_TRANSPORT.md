# Superbatch 11A: Byte-Safe Keychain Transport

Status: source repair and disposable acceptance only. Operational archive activation remains blocked.

## Transport decision

The macOS `security add-generic-password -w` CLI is rejected for secret transport. Two uniquely named disposable
experiments supplied canonical Base64 only through a protected stdin pipe. No secret appeared in process arguments
or command output, but the first newline-delimited attempt did not round-trip byte-for-byte and the EOF-delimited
attempt stored an empty password. Both exact disposable items were deleted and confirmed absent. No operational key
was created.

The operational adapter therefore uses the binary-length-aware Security.framework generic-password API directly.
It supplies the service, account and 32-byte key through memory buffers with explicit lengths. No key is serialized
into argv, environment variables, shell text, logs, exceptions or audit events. Exact service/account lookups reject
missing, duplicate, non-32-byte and ambiguous results. Deletion requires human authorization and is idempotent for
the exact service/account pair.

`SecurityCommandRunner` remains available only for bounded metadata operations. It uses absolute
`/usr/bin/security`, one fixed password-free existence query, `shell=False`, a fixed minimal locale environment,
bounded timeout, captured stdout and discarded stderr. It exposes no method that accepts stdin or requests a secret.

Canonical RFC 4648 Base64 helpers remain available for non-Keychain serialization boundaries. Exactly 32 input
bytes encode to 44 ASCII bytes matching `[A-Za-z0-9+/]{43}=`. Decoding permits no terminator, one LF, or one CRLF;
it rejects every other whitespace, extra line, invalid character, noncanonical padding and decoded length.

## Updated activation procedure

1. Review and checkpoint this source repair independently of operational activation.
2. From that exact clean commit, verify the operational service/account is absent without retrieving a password.
3. Create a uniquely named disposable item through `SecurityFrameworkAPI`, round-trip all 32 bytes, reject a
   duplicate, delete only that item and confirm absence.
4. Capture a rollback manifest before creating the dedicated environment, operational Keychain item or archive.
5. Install the separately hash-approved `cryptography` wheel only in the owner-only security environment.
6. Run the real AES-256-GCM and archive recovery suite before generating the operational key.
7. Generate the operational 32-byte key with the operating-system CSPRNG and write it through Security.framework.
8. Create the owner-only encrypted canary archive; keep the review service disabled and the preview unchanged.

No package, operational key, archive, service or source intake is created by this batch.
