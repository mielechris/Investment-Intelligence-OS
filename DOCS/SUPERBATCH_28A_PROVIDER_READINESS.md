# Superbatch 28A — provider readiness

Observed 2026-09-08 UTC from official Financial Datasets documentation: the fixed provider host is `api.financialdatasets.ai`; authentication is the `X-API-KEY` header; documented paths are `/prices/snapshot`, `/prices`, and `/company/facts`. The pricing table names IPOs, operating KPIs, forward guidance and non-GAAP metrics as multiplier-bearing premium datasets and states that all other endpoints count as one request on every plan. The three reviewed Stage A paths are not named premium datasets, so the bounded conclusion is one standard request for each of those paths only. No claim is made about unreviewed endpoints. No authenticated endpoint was contacted.

The observation identity is `financial-datasets-pricing-2026-09-08-v1`, observed at `2026-09-08T01:09:06Z` and expiring at the scheduled `2026-09-08T13:20:00Z` readiness gate. Operational material binds this identity, the official pricing URL and those UTC boundaries. A changed identity or expired observation fails closed and requires renewed owner review; neither the browser nor a background task refreshes pricing.

The original plan bound `fd-contract-v1`, establishing Financial Datasets as canonical. Its nine abstract `INSTRUMENT_PROFILE` identities were invalid. Provider plan v2 replaces each with a distinct `PRIOR_SESSION_BASELINE` identity using `/prices` and the source-controlled Friday, September 4, 2026 session. It is a bounded historical baseline, never company fundamentals and never a live backfill. The unsupported profile category remains a negative test only.

Official evidence: https://www.financialdatasets.ai/pricing, https://docs.financialdatasets.ai/api/prices/snapshot, https://docs.financialdatasets.ai/api/prices/historical, and https://docs.financialdatasets.ai/api/company/facts/ticker.

The readiness boundary uses only the fixed Financial Datasets selector already reviewed by IIOS. Presence and retrieval remain separate. This source batch performs neither. Browser output contains only readiness categories and counts. With a current reviewed cost document and fake AVAILABLE presence, fixture readiness is `PROVIDER_READY`; operational readiness remains unavailable until the presence probe and cost document are separately installed and authorized.

## Applicability and accounting

Each instrument has opening snapshot, point-in-time OHLCV, intraday snapshot and closing snapshot identities. MU additionally has one company-facts identity. The other nine instruments have one prior-session baseline identity. This produces exactly 50 unique identities: 10 opening, 10 OHLCV, 1 MU facts, 9 prior-session baselines, 10 intraday and 10 closing. All map to the three fixed paths. At one standard request each, exact and conservative worst-case cost are 50, leaving a 50-credit Stage A margin beneath the maximum of 100 and the daily ceiling of 200. Stages B and C remain locked.

Costs use integer request-credit units. Zero-cost repeats are permitted only after an authenticated cache hit proves that no outbound transmission occurred. Before any future transmission, the operational layer must atomically reserve the documented worst-case charge. Confirmed success finalizes it; explicit pre-transmission rejection releases it; possible-transmission timeout becomes an ambiguous charge and is never retried automatically. Stage A may not exceed 100 and the daily ceiling remains 200.

## Least-authority boundaries

The presence adapter fixes the committed Financial Datasets service/account selector internally and exposes no value-retrieval method. A separately authorized outbound adapter must retrieve the opaque value only immediately before one fixed request, hold it only in memory, transmit it only as `X-API-KEY`, and drop its reference afterward. Browser and command-line input cannot select a Keychain record.

The transport test seam permits only the fixed host and endpoint map, HTTPS production semantics, bounded timeouts, a one-megabyte response ceiling, JSON content, sanitized errors, and one attempt. It accepts no arbitrary URL, redirect, cookie, proxy setting, browser route, retry, provider-control operation, or trading capability. Production networking remains absent/disabled in this checkpoint.
