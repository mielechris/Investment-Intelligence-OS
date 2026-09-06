# Superbatch 23 — licensed listed-security source acceptance

## Decision

The listed-security adapter is fixture-tested and **not activated**. Financial Datasets is first priority. The
owner-confirmed configured account tier is `FREE`; no paid Credits balance or paid endpoint entitlement has been
demonstrated. Public terms permit internal and product use on every
self-serve plan and reserve redistribution of underlying data to Scale or a separate agreement. Those public
terms do not prove the configured account's tier, entitlement, attribution obligations, or browser-display
rights. A configured credential and a Free account do not prove paid Credits entitlement. No credential was
accessed and no request was made.

Before a live request, the owner must provide a dated purchase receipt or dashboard export demonstrating the
paid Credits balance, plus written confirmation
that the intended local browser display is internal product use rather than redistribution. The review must also
record real-time and historical-price entitlement, coverage, request cost, history depth, timestamp semantics,
attribution requirements, retention limits and prohibited uses. Until then the fixed state is
`FREE / PAID_CREDITS_NOT_DEMONSTRATED / LICENSE_REVIEW_REQUIRED`.

FMP remains second priority and `LICENSE_REVIEW_REQUIRED`; its public plan information is not substituted for
account-specific rights. Existing sanitized IIOS artifacts remain third priority. SEC and issuer evidence is
supplementary primary-source verification, not a market-data replacement. Koyfin and Market Vision remain manual
licensed research sources and are never automated by this adapter.

## Contract

The immutable identity is `NASDAQ:MU`, common stock, USD. Evidence carries observation, provider and retrieval
timestamps separately, including observation and effective time; fixed freshness/session categories; explicit raw/adjusted basis; availability booleans
instead of inferred prices or volumes; liquidity availability; deterministic source hash; exact credit cost;
provider/tier/license provenance; and primary-source-verification status. Missing values remain unavailable.

MU may classify only into U.S. large-cap equities, sector/thematic ETFs, and broad/factor ETFs in this first wave.
Other governed listed-security product classes are enumerated for future separately licensed evidence. Product
classification grants no research conclusion, paper eligibility, order, broker, ledger, or execution authority.

The browser projection contains only identity, fixed truth states, availability booleans, product count, review
gates, per-product readiness categories and false authority. Spread/slippage remains explicitly `UNAVAILABLE` until a
separately licensed source supports a hypothesis. It omits prices, volume, hashes, timestamps, unrestricted provider fields, credentials,
paths and source bodies. The browser has no provider route and cannot cause acquisition through polling.

## Future bounded acceptance

After a human licensing record is approved and the account tier is verified, an authorized acceptance may use
the existing exact Keychain selector and verified TLS transport for one MU request only. It must reserve one
known standard credit, use no retries or redirects, enforce size and timeout bounds, validate the exact response
schema and ticker, perform a cache repeat with zero outbound requests, retain only governed normalized evidence,
and stop on the first credential, license, entitlement, schema, timestamp or accounting failure.
