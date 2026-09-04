# Superbatch 8: Official Acquisition, Secure Archive, and Interview Intake

Status: isolated and fixture-first. There is no scheduler, worker, LaunchAgent, provider credential, broker access,
or automatic acquisition. Transcription and provider cost ceilings remain **$0**.

## Official-source boundary

Acquisition requires an exact hostname allowlist, HTTPS on the default TLS port, a descriptive contact-bearing
user-agent, approved rights and access-policy review, at most three redirects, a timeout no greater than 30 seconds,
a response ceiling no greater than 10 MB, a nonnegative request interval, and no more than two retries. Every
redirect is validated before it is followed. Private URLs, embedded credentials, unknown rights, access-policy or
robots conflicts, paywall bypasses, oversized responses, and uncontrolled redirects fail closed with fixed categories.

No network work occurs merely by importing or constructing an adapter. The bounded urllib transport must be
constructed and called explicitly. There is no bulk mode or scheduler.

## Archive topology

The archive root and each layer are mode `0700`; records are mode `0600`. Writes use an owner-only temporary file,
flush and `fsync`, then same-directory atomic replacement. The record name is the SHA-256 digest of exact bytes.
An optional expected digest prevents source mutation.

- `original/`: restricted original-source evidence, never browser-readable.
- `notes/`: normalized notes, approved metadata, and short quotations.
- `claims/`: attributed extracted claims pending human review.
- `browser/`: strict scalar allowlist only; no documents, transcripts, URLs, local paths, or hidden reasoning.

Retention must be at least one day. Deletion requires human approval, and store/retain/delete actions require an
audit-manifest entry with actor, time, action, and immutable content hash.

## Human lifecycle

`DISCOVERED → RIGHTS_REVIEW → APPROVED | REJECTED → NORMALIZED → CLAIMS_PENDING_REVIEW`

Every transition requires human approval. `APPROVED` additionally requires permitted rights, verified attribution,
and explicit source approval. Claim extraction is blocked until normalization. The terminal claim-review state still
has no automatic Judgment Foundry write.

## Interview intake and transcription bake-off

Reviewed staging accepts only bounded WAV/MP3/M4A audio, MP4/MOV video, and TXT/Markdown text. It requires consent,
permitted use, explicit exclusion of employer/client-confidential material, confirmed Jesse identity, and a final
Jesse approval gate. Transcription, speaker attribution, correction, and professional approval remain separate queues.
No real Jesse file was inspected.

The bake-off interface records word error rate, exact speaker-label match, timestamp presence, latency, privacy,
retention, training-use policy, and projected cost. Unknown policy or cost fails closed. Paid adapters cannot run;
the only exercised adapter is a deterministic local/offline synthetic fixture.

## Bounded public-source acceptance — 2026-09-03

Maximum authorized: three documents and 10,000,000 bytes total. Actual successful retrieval: one document and
91,423 bytes. Temporary acceptance data was held under a mode-`0700` directory and removed after validation.

1. SEC Berkshire Hathaway Form 10-Q, accession `0001193125-26-341032`, official URL
   `https://www.sec.gov/Archives/edgar/data/1067983/000119312526341032/brka-20260630.htm`.
   The bounded request returned HTTP 403; zero document bytes were accepted or archived. No circumvention was tried.
2. Berkshire Hathaway 2025 shareholder letter, issuer URL
   `https://www.berkshirehathaway.com/letters/2025ltr.pdf`. Exactly 91,423 bytes were retrieved with SHA-256
   `8a7daf30955673a0f39611857c7663ca84431a5af33ca900a6e715fa5a1584ad`.

Only a 470-byte canonical metadata/note record and a 239-byte browser projection were written to the isolated
archive. No original document was copied into the archive; no claim, recommendation, profitability assertion, or
Judgment record was created. The normalized note records only that the issuer letter discusses stewardship,
financial strength, and disciplined capital allocation; quotation is empty.

## Remaining activation gates

- per-domain legal/rights and robots/access-policy approval with a reviewed allowlist;
- SEC fair-access operational user-agent/contact approval and a successful low-rate acceptance;
- human source reviewer identities and immutable audit-manifest persistence;
- encrypted-at-rest archive threat model, backup, retention, and deletion acceptance;
- reviewed upload UI and malware/media validation in an isolated process;
- provider privacy, retention, training, accuracy, diarization, current price, outage, and deletion review;
- explicit nonzero budgets if any paid provider is later approved;
- separate operational change review; preview projection remains GET/HEAD-only and authority remains false.
