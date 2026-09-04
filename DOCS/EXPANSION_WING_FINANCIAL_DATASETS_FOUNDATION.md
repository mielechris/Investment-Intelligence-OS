# Superbatch 13A: Financial Datasets governed integration foundation

Status: source-only, fixture-first, `DISABLED / CREDENTIAL_NOT_PROVISIONED`. No Keychain access, provider contact,
credit consumption, persistent service, market ingestion, or preview integration occurred in this batch.

## Provider identity and secret boundary

- Provider ID: `FINANCIAL_DATASETS`
- Provider name: Financial Datasets
- Exact API origin: `https://api.financialdatasets.ai`
- Authentication header: `X-API-KEY`; never a URL parameter or caller-supplied header
- Keychain service: `com.iios.expansion-wing.financial-datasets`
- Keychain account: `financial-datasets-api-key`

Financial Datasets is separate from Financial Modeling Prep. Its code never reuses the FMP provider ID, service
`com.iios.expansion-wing.fmp`, account `fmp-api-key`, schemas, endpoint registry, cache, accounting, or normalized
evidence. The existing reviewed binary-safe Security.framework adapter is the only permitted credential source.
Financial Datasets publicly documents the credential as a string supplied in the `X-API-KEY` header; it does not
publicly document a fixed provider length or alphabet. IIOS therefore treats it as opaque and applies a defensive
application boundary: 16--256 bytes of visible ASCII (`0x21`--`0x7e`), exactly one header value, no spaces, control
bytes, non-ASCII data, or known placeholders. This is not a claim about the provider's secret-generation format.
IIOS does not parse, normalize, trim, change case, pad, decode, or otherwise transform accepted credential bytes.

Credential creation, retrieval, deletion, revocation, and rotation are separately authorized operational actions.
The key may never appear in URLs, source, fixtures, argv, environment variables, logs, diagnostics, errors, browser
projections, screenshots, or test output. Missing, duplicate/ambiguous, malformed, inaccessible, wrong-context, or
out-of-bounds results fail closed using fixed categories. The general archive-key methods remain fixed at 32 bytes;
the explicitly bounded opaque-secret methods preserve the original Financial Datasets bytes exactly.

## Endpoint and capability registry

The adapter accepts no caller-supplied URL or authentication header. A capability selects a fixed registry entry.
Every request and redirect must remain HTTPS on exact host `api.financialdatasets.ai`, with no embedded credentials,
alternate port, IP literal, lookalike subdomain, query secret, or fragment.

Company facts uses the exact canonical path `/company/facts`, with no trailing slash. Authorization occurs against
that path before the deterministic `ticker=<approved identifier>` query is constructed separately. Duplicate slashes,
dot segments, percent-encoded substitutions, alternate paths, and path-correcting redirects fail closed. No path
normalization occurs after authorization, and redirects are never followed automatically.

| Capability | Classification | Credit class |
|---|---|---|
| Company facts and identifiers | SUPPORTED | STANDARD / 1 |
| Income statements | SUPPORTED | STANDARD / 1 |
| Balance sheets | SUPPORTED | STANDARD / 1 |
| Cash-flow statements | SUPPORTED | STANDARD / 1 |
| Combined financial statements | SUPPORTED | STANDARD / 1 |
| Financial metrics and ratios | SUPPORTED | STANDARD / 1 |
| Historical stock prices | SUPPORTED | STANDARD / 1 |
| Real-time price snapshots | SUPPORTED | STANDARD / 1 |
| SEC filing metadata | SUPPORTED | STANDARD / 1 |
| SEC filing item metadata | CONTRACT_ONLY | unknown / blocked |
| Earnings data | SUPPORTED | STANDARD / 1 |
| Press-release metadata | LICENSE_REVIEW_REQUIRED | unknown / blocked |
| Company-news metadata | LICENSE_REVIEW_REQUIRED | unknown / blocked |
| Insider transactions | LICENSE_REVIEW_REQUIRED | unknown / blocked |
| Institutional ownership | LICENSE_REVIEW_REQUIRED | unknown / blocked |
| Segmented financial statements | PREMIUM_SUPPORTED | PREMIUM / 8 |
| Operating KPIs | PREMIUM_SUPPORTED | PREMIUM / 8 |
| Forward guidance | PREMIUM_SUPPORTED | PREMIUM / 8 |
| Non-GAAP metrics | PREMIUM_SUPPORTED | PREMIUM / 8 |
| Central-bank interest rates | CONTRACT_ONLY | unknown / blocked |

`SUPPORTED` and `PREMIUM_SUPPORTED` here identify reviewed adapter contracts and deterministic fixtures. Exact live
endpoint availability, returned schema, plan entitlement, and third-party restrictions must still be checked against
official documentation before activation. Anything not assigned a reviewed path and known cost is rejected before a
request. Unknown fields are counted and discarded; they never silently enter normalized evidence.

## Credit accounting and resource limits

The purchased Credits-plan ceiling is 1,000. Auto-reload, purchase, refill, subscription upgrade, and overage are
prohibited. Standard attempts reserve 1 credit; Premium attempts reserve 8 credits. Unknown cost or balance,
insufficient allowance, or a pre-transport failure releases or prevents the reservation. Once transport begins, an
attempt without a confirmed response remains conservatively charged as ambiguous; a confirmed response is charged
exactly once. Cache hits and deduplicated single-flight waiters cost zero. There are no automatic retries. Accounting
uses one lock across total, daily, and monthly counters.

The next operational acceptance ledger starts at confirmed consumed `0`, prior ambiguous/reserved `1`, and maximum
remaining authorized `999`. These are conservative IIOS values, not a claim about the provider-reported balance. An
owner may inspect the provider dashboard manually without copying, displaying, or recording the API key; dashboard
evidence remains separately attributed and never silently rewrites IIOS attempt history.

Initial limits are 10 requests/minute, 100 credits/day, 1,000 credits/month, and 1,000 total. Internal daily/monthly
ceilings may be lowered but never exceed the provider balance or total ceiling. Batch size is at most 50 shortlisted
symbols. Full 519-symbol provider scanning and uncontrolled per-symbol fan-out are prohibited. The existing IIOS
scanner remains discovery owner.

The browser/accounting boundary exposes only provider state, capability, Standard/Premium class, projected cost,
consumed and remaining authorized credits, cache Boolean, request timestamp, response status category, and fixed
failure category. It excludes credentials, parameterized URLs, response bodies, company values, text, and evidence.

Before transport, IIOS creates a scalar-only attempt record in `AUTHORIZED`, then moves to `REQUEST_STARTING`. Every
branch terminates as `RESPONSE_OBSERVED`, `TRANSPORT_FAILED`, `REDIRECT_REJECTED`, `TIMEOUT`, `TLS_FAILED`,
`DNS_FAILED`, or `ACCOUNTING_UNCERTAIN`. Records contain only fixed identifiers, an approved symbol, projected cost,
sequence, request/response Booleans, fixed status, bounded metrics, cache/retry state, and accounting category.
Missing metrics and callback failures remain explicit; code never indexes an assumed metric.

## Cache, classification, provenance, and verification

Identical capability/ticker work has one single-flight owner and a five-minute maximum cache. Capability-specific
freshness limits are stricter for price observations. Cache keys contain capability and bounded ticker tuple only—no
credential. Cache entries contain governed normalized records, never raw bodies.

Each record carries provider ID, capability, ticker, request time, provider publication time when supplied,
filing/report period, accession or official-source URL when supplied, freshness, normalized hash, schema version,
classification, verification state, credit cost, and cache state. Future evidence and timezone-ambiguous timestamps
are rejected.

## Verified TLS transport and isolated trust bundle

Framework Python 3.14.7 linked to OpenSSL 3.5.7 had no configured default CA file or directory. DNS and TCP succeeded,
and the system trust client verified the server chain, while Python failed with issuer-chain verification code 20.
IIOS therefore rejects global certificate installation, changes to the preview environment, verification bypass,
trust-on-first-use, and leaf-certificate pinning as remedies. CA-bundle verification establishes a reviewed set of
certificate authorities while retaining normal chain and hostname verification; it is not certificate pinning.

The dedicated Financial Datasets transport uses `PROTOCOL_TLS_CLIENT`, `CERT_REQUIRED`, hostname checking, TLS 1.2 or
newer, and exact host/SNI `api.financialdatasets.ai` on port 443. It has no insecure or framework-default fallback.
Network remains disabled by default. A caller must supply a regular, owner-readable, nonsymlink CA bundle that is not
group/world writable, is nonempty and bounded, contains PEM certificates, and exactly matches a separately reviewed
SHA-256. Bundle paths and certificate material never enter errors, reports, audit records, or browser projections.
Trust is revalidated on process startup and before transport construction.

Trust states are `NOT_CONFIGURED`, `BUNDLE_MISSING`, `BUNDLE_UNSAFE`, `BUNDLE_HASH_MISMATCH`, `BUNDLE_INVALID`,
`READY`, `TLS_VERIFICATION_FAILED`, and `CONTEXT_RESTRICTED`. Only `READY` constructs an operational context. Fixed
failures distinguish missing/unsafe/mismatched trust, certificate-chain and hostname failures, TLS protocol failure,
timeout, DNS, TCP, proxy/context rejection, and residual accounting uncertainty. HTTP 401/403 require an observed HTTP
response and remain authentication/entitlement failures rather than TLS failures.

The initial proposed trust source is a pinned `certifi` wheel installed only in a dedicated Financial Datasets
environment. Activation must first retrieve official PyPI metadata in a separately authorized batch, establish the
exact version, binary wheel filename, wheel SHA-256, and embedded metadata, then install binary-only with complete hash
locking. No version or hash is assumed here. After installation, hash the resulting `cacert.pem` into a sanitized trust
manifest. Do not install a source distribution, modify global Python, or modify the preview environment.

Activation sequence: verify the wheel and bundle hashes; verify permissions and expiry-review policy; run a
credential-free TLS-only handshake with exact SNI/hostname; then obtain fresh authorization for MU-first acceptance.
The bounded runner checks trust before Keychain access, starts with two prior ambiguous credits and 998 maximum
remaining authorization, performs no retries, and blocks AMD unless MU and its zero-cost cache repeat are fully valid.
Provider dashboard balance remains distinct from conservative IIOS accounting.

Rollback removes only the dedicated environment and reviewed trust manifest after stopping its isolated process. It
does not alter global trust, the preview runtime, or the Keychain credential. Trust-bundle updates require a new
official wheel/hash review, TLS-only acceptance, expiration review, and separate activation approval.

Classes remain distinct: `PRIMARY_SOURCE_FACT`, `PROVIDER_NORMALIZED_FACT`, `DERIVED_METRIC`, `ANALYST_ESTIMATE`,
`COMPANY_GUIDANCE`, `NEWS_METADATA`, `PRESS_RELEASE_METADATA`, `INSIDER_DISCLOSURE`, `INSTITUTIONAL_HOLDING`,
`TECHNICAL_OBSERVATION`, and `UNVERIFIED_PROVIDER_VALUE`. Provider output is informational. Material claims require
primary-source verification and human approval before Judgment Foundry, Pattern Laboratory, Committee reliance, or
Failure Museum use. Paper-position proposals remain false even after verification. No record can create a
recommendation, order, position, fill, ledger write, threshold change, or live execution.

## Licensing boundary

Reviewed self-serve terms are represented as permitting commercial/internal/business use and incorporation into an
internally built application. Underlying data redistribution is prohibited without an appropriate plan or agreement;
IIOS must not become a substitute feed or competing dataset. Provider and third-party market-data restrictions remain
under continuing review. Access ends when the license or paid credits end. On termination, cached licensed values and
derived records subject to deletion must enter a separately authorized, auditable deletion workflow; source-owned
primary evidence and non-provider audit metadata must be classified independently.

The state machine is `REVIEWED_INTERNAL_USE`, `LICENSE_REVIEW_REQUIRED`, `REDISTRIBUTION_PROHIBITED`, `TERMS_CHANGED`,
or `ACCESS_TERMINATED`. Only `REVIEWED_INTERNAL_USE` permits an otherwise authorized request. Terms uncertainty or
material change fails closed. No browser display of licensed underlying data is approved by this batch.

## Fixture acceptance

Synthetic fixtures use only `MU` and `AMD` as public identifiers. They cover company facts, income statements, price
snapshots, filing metadata, and earnings estimates. Synthetic values are explicitly fixtures and are not represented
as live Financial Datasets output. Tests cover Standard/Premium accounting, cache repeat, single-flight, partial
outage, stale and future evidence, authentication, exhaustion, unknown cost, malformed/oversized responses, timeout,
terminal no-retry, redirect rejection, secret containment, and FMP selector separation. Ordinary test discovery makes
zero provider or Keychain calls.

## Exact later activation sequence

1. Review and checkpoint this source-only batch.
2. Reconfirm the clean reviewed SHA.
3. Reconfirm the Financial Datasets key has never been exposed.
4. Separately authorize provisioning through the binary-safe Security.framework ceremony using the exact selector.
5. Verify fresh-process persistence without printing the credential.
6. Reverify official endpoint documentation, license state, 1×/8× costs, balance, deletion duties, and schema.
7. Initialize accounting with confirmed `0`, prior ambiguous `1`, and maximum remaining `999`.
8. With fresh explicit authorization, run canonical `/company/facts` for `MU` first; stop before `AMD` on any failure.
9. After each success, run one identical cache repeat, which must consume zero requests and credits.
10. Report attempted, confirmed, and ambiguous requests plus latency, size, schema, freshness, and hashes without bodies.
11. Retain only approved normalized governed evidence and sanitized coverage metadata.
12. Remove only temporary runtime material and stop before continuous scanning or preview integration.
13. Require separate approval for scheduled ingestion, persistent service changes, or further endpoints.

Any credential, licensing, authentication, schema, accounting, host, or Keychain failure stops without retrying a
terminal failure or weakening a gate.

## Rollback and limitations

Before activation, rollback is source-only removal of this module, its two manifests, tests, and document. After an
authorized bounded acceptance, stop only the isolated process and remove only its temporary runtime. Do not delete,
revoke, or rotate the persistent credential without explicit authorization. If license access ends, disable the
adapter before separately reviewing required data deletion.

Known limitations: live schemas and entitlements are not yet proven; several capabilities remain contract-only or
license-review-required; no browser integration exists; no continuous scan is permitted; no provider fallback exists;
and the persistent preview remains on its prior committed build.
