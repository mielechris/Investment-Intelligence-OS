# Expansion Wing Superbatch 14B — Candidate-Flow Acceptance

## Classification

This is a fixture-only acceptance contract. It proves the handoff from a bounded sanitized scanner batch through the
14A enrichment bridge into a primary-source-review queue. Provider network access, Keychain access, continuous
scheduling, committee reliance, recommendations, orders, brokers, ledgers, and live execution remain disabled.

## Input boundary

The batch has an opaque ID, timestamp, exact existing-scanner identity, and one to five candidates. Candidate records
contain only an opaque candidate ID, ticker, discovery time, and the already approved company-profile or identifier
gaps. Unknown fields, alternate scanners, malformed IDs, invalid tickers, unsupported gaps, replays, and oversized
batches fail before provider work.

## Durable accounting

The initial checkpoint represents the live-accepted baseline: three confirmed plus two ambiguous credits, five used,
and 995 remaining. Confirmed and ambiguous values remain separate. A hash-linked scalar checkpoint is owner-only,
bounded, atomically replaced, directory-synced, and protected by compare-and-swap against the prior event hash.

Each acceptance compares the provider ledger to the durable checkpoint before enrichment. A mismatch or replay stops
before work. Any simulated credit change is checkpointed even if a later fixture provider response fails. The file
contains no ticker, candidate, fact, hash, credential, URL, response, recommendation, or source content.

## Output boundary

Successful evidence is queued as `PRIMARY_SOURCE_REVIEW_REQUIRED`. The internal queue item binds an opaque candidate,
ticker, and normalized record hash. Browser-safe projection exposes only aggregate candidates, unique tickers,
provider requests, cache hits, starting/ending/new credit totals, and primary-review queue size.

No acceptance result grants provider activation, continuous scanning, automatic promotion, committee reliance,
Judgment Foundry writes, Pattern Laboratory submissions, paper orders, ledger writes, broker connectivity, or live
execution.

## Future activation

A later live acceptance requires a new reviewed commit and explicit authorization. It must begin from the durable
five-credit baseline, use at most five sanitized real scanner candidates, check cache first, cap new Standard credits
at five, persist accounting on every terminal outcome, and stop before scheduled operation or downstream promotion.
