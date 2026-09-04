# IIOS Provider-Neutral Market Enrichment

Status: fixture-first contracts only. Provider activation, credentials, external requests, Koyfin import, and
provider-derived execution are `NOT_ACTIVATED`. The existing 519-symbol IIOS scanner remains the exclusive discovery
owner. This batch does not modify 9A, 9B, 9E, 9H, 9I, 9J, the paper fund, or the persistent preview.

## Capability boundary

The provider-neutral interface identifies company profiles and identifiers, financial statements, ratios, historical
prices, analyst estimates with revision timestamps, earnings calendars, company-news metadata, forex and crypto
reference data, and commodity data only where a provider explicitly declares that capability. Every scalar datum
records provider, endpoint capability, observation/publication/retrieval times, point-in-time cutoff, freshness,
rights/license state, response hash, verification state, and one semantic class: fact, estimate, opinion, prediction,
derived metric, or technical observation.

No cross-provider field substitution is allowed. A missing capability is `UNAVAILABLE`; a mixed response is
`PARTIAL_PROVIDER_OUTAGE`. Material claims require primary-source verification. Enrichment may prepare bounded packets
for research agents, Pattern Lab, and the Investment Committee, but has no direct execution route.

## FMP adapter contract

The FMP adapter is disabled by default and contains no network implementation or credential value. The persistent FMP
account's API key must be provisioned through the reviewed macOS Security.framework adapter under the exact dedicated
selector service `com.iios.expansion-wing.fmp`, account `fmp-api-key`. It may be retrieved only inside an isolated,
separately authorized coverage-test process. It must never enter source, fixtures, argv, environment variables, logs,
reports, browser projections, test output, or screenshots. A future caller must separately prove provider enablement,
credential availability, approved license, and approved endpoint.
Its injected transport is constrained to the exact HTTPS identity `https://financialmodelingprep.com`, at most one
redirect, a 5-second default timeout, 2 MB maximum body, one retry, bounded backoff, 10 requests per minute, 50 symbols
per batch, 5-minute cache, and one single-flight owner for identical work. Unknown response fields are ignored by
default or rejected under strict mode. Fixed error categories replace provider bodies and exceptions.

Per-capability request counts are recorded. Cost remains unknown and activation fails closed until the chosen plan's
current price, quotas, permitted automation, internal use, storage, and display terms are approved. No API key may
appear in source, arguments, environment-derived diagnostics, logs, exceptions, cache keys, or browser projections.

## Planning envelope: no more than $100/month

The proposed architecture is a budget envelope, not a claim about current vendor prices:

1. Existing IIOS remains the scanner and discovery owner at its existing cost.
2. FMP Premium is the proposed autonomous enrichment role only if current licensing, endpoint coverage, quotas, and
   price fit inside the approved envelope after testing. Otherwise it remains disabled or a lower plan is evaluated.
3. Koyfin Plus is only a `HUMAN_RESEARCH_COCKPIT`. It is not scraped, polled, authenticated by IIOS, or treated as an
   autonomous feed. Optional manual notes/CSV remain disabled until measured trial utilization and license review show
   a distinct need.
4. SEC/issuer, USDA, EIA, EPA, and Federal Reserve/FRED data are candidate primary verification sources, each behind
   its own access-policy, series, vintage, attribution, and redistribution review.
5. Market Vision remains the existing `SECONDARY_DOMAIN_EXPERT` registration in `RIGHTS_REVIEW_REQUIRED / REPORTED`;
   this batch does not duplicate or alter that implementation.

Hard ceiling: **$100 per calendar month**, with no overage, automatic upgrade, cross-provider fallback, or purchase.
The implementation batch costs **$0**. Current paid-plan prices are intentionally `null` in the capability audit and
must be reverified directly during a separately approved procurement review.

## Expected request volume

Initial coverage testing is limited to the five-entry research watchlist and one requested capability per batch.
Nominal test envelope: at most 5 symbols per batch, 10 provider requests per minute, 100 requests per day, and 1,000
requests per month. Cached or duplicate work does not issue a request. Production sizing requires measured cache-hit
rate, missing-field density across the 519-symbol universe, endpoint batch support, quota headroom, and exact
per-endpoint accounting. A one-request-per-symbol design is rejected.

## Free FMP coverage-test procedure

This procedure is documentation only and is not authorized by this batch:

1. Reverify the official Free-plan price, terms, automation permission, quotas, endpoint list, retention, and display
   rules; record `LICENSE_REVIEW_REQUIRED` until written review is complete.
2. Separately authorize Keychain provisioning and store the persistent account key through the reviewed
   Security.framework adapter using the exact dedicated selector. Provider contact is a different authorization.
3. Use a new isolated fixture-compatible runtime; keep the persistent preview unchanged.
4. Request only the missing company-profile capability for `MU` and `AMD` as one batch if the endpoint supports it.
5. Cap the test at one successful request plus one controlled cache repeat; prohibit retries after a terminal quota or
   authorization response.
6. While licensing remains pending, retain only endpoint/capability, HTTP status category, response byte count,
   latency, returned top-level field names, schema-match status, timestamp availability, freshness, content hash,
   cache/accounting results, and fixed sanitized failures. Do not persist profile or statement values, estimates,
   prices, news, response bodies, or normalized security evidence.
7. Use `MU` and `AMD` only as public test identifiers; do not retain their returned values.
8. Remove only temporary runtime material. Do not rotate, revoke, or delete the persistent FMP key without separate
   authorization. Do not promote any claim.

## Upgrade scorecard

Upgrade consideration requires all of: exact plan cost within the $100 ceiling; written automated-scanning and
internal-storage permission; required endpoint coverage; usable revision/publication timestamps; point-in-time
suitability; batch support; acceptable quota and cache economics; deterministic schema pass rate; bounded outage and
rate-limit behavior; primary-source verification coverage; and a demonstrated material gap not already filled by
IIOS. Any unknown is a failed gate. Koyfin utilization is scored separately as human workflow value and can never
justify autonomous access.

## Rollback

No runtime is installed by this batch. Source rollback is removal of the provider-neutral module, disabled FMP
adapter, three fixture/audit manifests, focused tests, and this document before commit. A future activated adapter must
support a narrow rollback: disable its explicit activation gate, stop only its isolated temporary process, remove only
its cache/runtime directory, and confirm existing IIOS scanner and 9A–9J state are unchanged. The persistent FMP key
must not be rotated, revoked, or deleted unless that exact action receives separate authorization. Provider data must
never be needed to recover paper-fund truth.

## Authority invariants

Credential exposure, broker connectivity, ledger write, paper-order creation, live execution, automatic threshold or
weight changes, Judgment Bank automatic writes, and provider activation are always false. Watchlist membership is
research inventory—not ownership, a recommendation, paper eligibility, or permission to trade.
