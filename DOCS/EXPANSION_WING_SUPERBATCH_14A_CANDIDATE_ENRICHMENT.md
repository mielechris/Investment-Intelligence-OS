# Expansion Wing Superbatch 14A — Governed Candidate Enrichment Bridge

## Purpose

This fixture-first bridge allows candidates already discovered by the existing governed 519-symbol IIOS scanner to
request narrowly scoped Financial Datasets company facts. It does not discover securities, activate a provider,
schedule work, make recommendations, or create orders. Financial Datasets remains an enrichment source rather than
the factory's discovery owner.

## Accepted input

Each input carries an opaque candidate ID, validated ticker, discovery timestamp, exact originating scanner, and an
allowlisted missing-field request. The only supported fields are `company_profile` and `identifiers`, both mapped to
the live-accepted `COMPANY_FACTS` capability. The initial ceiling is five candidates and five new Standard credits.
Duplicate tickers are collapsed before provider work.

The bridge is disabled unless both its policy and the individual run are explicitly enabled. It checks the existing
provider cache before paid transport. Company facts remain one ticker per request. Partial provider failures stop the
batch, expose no partial evidence packet, and trigger no fallback provider.

## Accounting checkpoint

The persistent conservative baseline after bounded acceptance is three confirmed credits plus two ambiguous credits:
five total used and 995 remaining under the 1,000-credit ceiling. The provider ledger now represents prior confirmed
and ambiguous consumption separately. Fixture tests begin from this exact baseline. Browser projection exposes only
counts and credit totals, never tickers, candidate IDs, hashes, facts, credentials, paths, or provider bodies.

## Evidence and routing

Successful results bind the opaque candidate to a governed normalized record, normalized hash, unavailable provider
timestamp, unknown freshness, and `PRIMARY_SOURCE_REQUIRED` verification state. The full evidence remains internal;
the browser sees only aggregate counts.

Primary-source verification plus human approval can make the facts available to a research-review context. It still
does not grant committee reliance, Judgment Foundry writes, Pattern Laboratory submission, paper orders, ledger
writes, broker access, or live execution. Those surfaces require separate future contracts and review.

## Activation boundary

Superbatch 14A performs fixture validation only. It does not access Keychain, contact Financial Datasets, consume
credits, modify the persistent preview, or install a scheduler. A future candidate-flow acceptance must start from a
reviewed clean commit, use a bounded sanitized candidate fixture, retain the five-credit baseline, and stop on the
first failed gate. Continuous 519-symbol provider enrichment is prohibited.
