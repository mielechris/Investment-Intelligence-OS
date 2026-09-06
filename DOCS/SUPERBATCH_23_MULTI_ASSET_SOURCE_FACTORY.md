# Superbatch 23A–23Z — governed multi-asset source factory

## Activation state

All source families are fixture-complete and operationally `NOT_ACTIVATED`. No Keychain item was read, no
external endpoint was contacted, and zero credits were consumed. A credential proves authentication only; it
does not prove entitlement. Browser polling owns no acquisition, budget, provider or publication route.

## Entitlement registry

| Provider | Intended role | Current approval | Automation | Owner evidence required |
|---|---|---|---|---|
| Financial Datasets | Listed equities/ETFs, fundamentals and licensed price evidence | FREE / UNAPPROVED FOR LIVE ACCEPTANCE | Disabled | Dated paid Credits purchase/balance evidence, internal/display/retention/attribution, real-time/delayed/history and exact request cost |
| Financial Modeling Prep | Secondary listed-security fallback | UNAPPROVED | Disabled | Same complete account-specific rights record and endpoint entitlement |
| SEC EDGAR | Supplemental primary filings | UNAPPROVED | Disabled | Approved access policy, user agent, retention and rate policy |
| Issuer official | Supplemental issuer facts | UNAPPROVED | Disabled | Exact domain, rights, access policy and point-in-time approval |
| Koyfin manual cockpit | Human research notes only | UNAPPROVED | Prohibited | Subscription rights and reviewed manual excerpt policy |
| Market Vision | Physical-commodity practitioner hypotheses | UNAPPROVED | Prohibited | Subscription rights and reviewed notes/quotation policy |
| Sanitized IIOS | Existing governed operational truth | UNAPPROVED for this wave | Read-only contract | Exact sanitized artifact/schema approval |

The Financial Datasets tier is known as Free, but a paid Credits balance has not been demonstrated; therefore
`permits_request` remains false. Other unknown values remain unknown. Owner approval requires an opaque owner ID and
UTC timestamp. Manual sources cannot have credential selectors or autonomous adapters.

## Product-source matrix

The registry has exactly 24 products and one independent synthetic $10,000 comparison account per product.
The operational $10,000 paper fund is separate. In the no-entitlement state, 22 desks are `UNAVAILABLE` and the
two options desks are `RESEARCH_ONLY_UNPRICEABLE`. Complete fixture envelopes exercise:

- Equity/ETF: identity, venue/session, raw/adjusted basis, corporate actions, volume, liquidity, benchmark,
  spread, slippage, fees and point-in-time provenance.
- Treasury/credit: issue and maturity, coupon, clean/dirty basis, yield convention, accrued interest,
  duration/convexity, quality, call/security state, settlement, liquidity, tax and proxy distinctions.
- Options: synchronized underlying/contract time, expiry, strike, type/style/multiplier, bid/ask/mark, volume,
  open interest, IV/Greeks, assignment/early-exercise, loss/break-even and costs.
- Commodity/futures: exposure type, month, multiplier/tick, settlement, expiry/roll, curve/carry, tracking,
  liquidity and license.
- FX: pair convention, reference venue, bid/ask, weekly session, liquidity, carry/rollover and proxy basis.
- Crypto: asset/reference venue, spot/proxy exposure, 24/7 calendar, evidence timestamp, liquidity, custody and
  structural warnings, and listed-product market-hours differences.
- Listed income: distribution basis, duration sensitivity, liquidity, call/redemption, expense, premium/discount
  and credit exposure.

A proxy never becomes its underlying. Market availability never implies evidence availability. One family
failure cannot change another family's state, and retained evidence must retain its original timestamp and become
stale rather than being silently carried forward as current.

## Monday rehearsal

1. Verify the clean reviewed commit and all protected service identities.
2. Validate all seven entitlement records; stop each provider independently on an unknown field.
3. Keep every provider switch disabled. Validate fixture envelopes for all eight source families.
4. Exercise the 17 deterministic scenarios: current, delayed, unavailable, rights failure, credit exhaustion,
   stale, future, proxy-only, unpriceable options, incomplete bonds, provider failure/recovery, zero/valid/invalid
   lineage, synthetic observation and zero operational paper activity.
5. Verify 24 independent synthetic bases, the separate operational fund, zero operational activity and all false
   authority. Record only sanitized results.

## Tuesday pre-market and opening sequence

1. Reverify entitlement evidence date, owner approval, tier, coverage, retention, display rights and request cost.
2. Verify fixed origin/path, trusted TLS, exact credential selector and conservative credit balance without
   exposing the credential. Verify market session and effective-time policy.
3. Open source waves independently: listed equity, rates/credit, options, commodity, FX, crypto, income.
4. A wave opens only after its family schema, freshness, cost, proxy and completeness gates pass.
5. For the separately authorized first live wave, make exactly one MU request, no retry. Sanitize immediately,
   record one credit and latency, and prove the provider body cannot reach the browser.
6. Candidate creation remains a later human-governed step. No operational paper action is allowed.

## Intraday supervision and credits

- Enforce fixed provider, daily and per-cycle budgets; zero retry; bounded timeout/size; single flight.
- Browser polling cannot request data or change budgets. Each source reports its source, blocker and timestamp.
- On timeout, schema, license, future-time or budget failure, stop that provider wave only. Do not erase authentic
  retained evidence or retimestamp it.
- Display licensed values only when the entitlement record explicitly permits browser display.

## Post-close audit, disable and rollback

Reconcile request attempts, confirmed/ambiguous credits, cache hits, retained hashes, timestamps, product states,
synthetic observations and zero operational activity. Provider disable is a fixed configuration gate performed
outside the browser; it does not delete authentic evidence. Roll back only the new source adapter/projection and
entitlement configuration. Never alter the operational ledger, projection publisher, protected services or the
separate paper fund.

## Owner evidence checklist

- Provider legal name, exact account tier and dated invoice/dashboard proof
- Contract/terms version and evidence date
- Internal application/research permission
- Browser display versus redistribution classification
- Real-time, delayed and historical entitlement and coverage
- Timestamp/effective-time guarantees and adjustment/corporate-action methodology
- Attribution and retention requirements; prohibited uses
- Exact endpoint request cost, purchased balance, daily/cycle ceiling and rate limit
- Approved credential selector (never the credential value)
- Opaque owner approval identity and UTC approval timestamp

Until every applicable item is present, external acceptance is blocked with `ENTITLEMENT_UNAPPROVED`.
