# Expansion Wing Provider Requirements and Cost Comparison

No provider is selected, installed, authenticated, or activated by this branch. Adapter interfaces return `UNAVAILABLE` until a public source or explicit fixture callback is supplied.

| Domain | Minimum data | Freshness / timeout | Preferred first tier | Cost posture | Promotion blockers |
|---|---|---|---|---|---|
| Equity and sector ETF | Quote, volume, corporate actions, venue/timestamp | 5 minutes / 2 seconds | Existing legally accessible market source | Reuse existing/free before paid | Unclear redistribution rights, missing timestamps |
| Treasuries and bonds | Yield, maturity, duration, credit quality, price convention | 60 minutes / 3 seconds | U.S. Treasury/FRED/issuer or regulator publications | Free public sources first | Stale curve, ambiguous pricing, missing identifiers |
| IPO/new listing | Filing, exchange notice, listing date, range, float, lockup | 60 minutes / 3 seconds | SEC and exchange publications | Free public sources first | Unattributed calendar, missing filing lineage |
| Commodities/futures | Contract specs, settlement, size, margin, expiry, roll calendar | 5 minutes / 2 seconds | Exchange-published delayed/public data | Compare delayed/free against licensed feeds | Missing leverage, expiry, rollover or overnight-risk data |
| Investor intelligence | URL, author/publisher, publication/access dates, permitted use | 24 hours / 5 seconds | Issuer filings, letters, lectures, podcasts, papers | Public/legal sources only | Paywall/license ambiguity, complete-work storage |
| Interview media | Owned upload metadata, consent, allowed use, transcript and speakers | Offline bounded job | Local/open transcription evaluation before paid API | Compare per-minute price, diarization, retention | Missing consent, retention control, transcript approval |

## Selection scorecard

Any future provider review must compare: authoritative provenance, point-in-time timestamps, revision history, asset coverage, latency, outage behavior, redistribution/license terms, retention/privacy, deterministic request limits, bounded timeout support, batch pricing, per-request/per-token/per-minute pricing, minimum commitments, cancellation/export, and a hard daily cost ceiling. Unknown price must fail closed; professional status or provider popularity is not evidence quality.

## Adapter boundary

Adapters expose provenance, observation time, freshness, content hash, duplicate state, fixture state, sanitized error class, and explicit availability. They never expose credential values. The callback adapter has a bounded timeout and is deliberately unconfigured. Artifact adapters accept only bounded JSON files and never import the operational ledger.
