# Superbatch 24 — Tuesday market evidence and paper operations

This batch is fixture-first and disabled by default. It adds governed composite evidence, ten explicit pilot listed products, a budgeted Tuesday controller plan, paper-cost assumptions, synthetic-sleeve separation, rehearsals, and a 24-room truth board. It does not activate a controller, scheduler, broker, ledger, or operational paper position.

## Evidence contract

Observed snapshot and historical OHLCV remain separate from derived median volume and median dollar volume. Every derived value carries its formula version, input timestamps and hashes, lookback, units, missing-input behavior, and effective timestamp. Missing volume is unavailable, never zero. Daily volume does not establish order-book depth or bid/ask liquidity.

Financial Datasets documentation available for `/prices` describes OHLCV fields but does not state whether the history is raw, split adjusted, dividend adjusted, or fully adjusted. The governed classification is therefore `UNSPECIFIED`; the public browser state is `UNAVAILABLE`, and methods requiring adjusted history remain ineligible. Price behavior is never used to infer corporate actions.

The paper cost model is a conservative, versioned assumption. Observed spread, estimated spread, slippage, commissions/fees, and total modeled cost remain distinct. It is never a quote. Methods requiring actual bid/ask evidence remain blocked.

## Forward-only adjustment boundary

`FORWARD_ONLY_UNADJUSTED_OBSERVATION` stores a current authenticated snapshot as time zero and accepts only later authenticated marks. It makes no adjusted-history, historical-return, or total-return claim, and never uses the unspecified historical price series as an actionable signal. Mean reversion, historical momentum, trend following, historical pairs/relative value, backtested volatility, drawdown, total return, and historical calibration fail with `ADJUSTMENT_BASIS_UNSPECIFIED`.

Long-horizon fundamental, event-driven, catalyst/news reaction, policy/macro regime, independently corroborated professional-method, and forward-price tracking research may be considered prospectively only after their separate thesis, source, candidate, committee, risk, session, timestamp, liquidity-proxy, cost, and budget gates pass. Registration alone grants no eligibility.

Historical OHLCV is historical research evidence; a current snapshot is current evidence; future snapshots are forward marks; corporate actions are a separate evidence stream. Daily volume may support only a labeled `DAILY_VOLUME_PROXY_NOT_ORDER_BOOK`. Observed spread remains unavailable. Modeled cost remains `PAPER_COST_ASSUMPTION_NOT_MARKET_QUOTE`, and an execution-quality claim is prohibited.

A detected or unreconciled split, dividend, merger, ticker change, or other corporate action suspends the sleeve as `INCOMPLETE_CORPORATE_ACTION`. No return crosses that boundary. Existing marks are immutable unless an explicit audited normalization event is separately approved.

Licensed market data may establish market price evidence after entitlement review. Security identity should be cross-checked with an exchange or issuer. Thesis and catalyst claims require SEC filings, issuer releases, or other appropriate primary evidence. Market-session status requires an approved exchange/calendar source. Independent corroboration is required where the applicable evidence policy says so; an issuer source is not required merely to repeat each licensed market price.

## Governed pilot registry

The reviewed pilot is MU, SPY, XLK, VNQ, TLT, GLD, UUP, IBIT, PFF, and BIL. Registration is not activation, entitlement, completeness, or recommendation. One product’s success cannot promote another.

The bounded September 6 acceptance made exactly one snapshot and one daily-history request for each pilot: 20 attempts, 20 accepted responses, no retry, no ambiguity, and 20 confirmed new credits. Each history response contained 20 authenticated OHLCV observations with the documented schema. Because adjustment treatment remains unspecified, all ten results are `RESEARCH_OBSERVATION_INCOMPLETE_ADJUSTMENT_UNSPECIFIED`; none is adjusted-history, candidate, research, or paper eligible. Combined accounting is 22 confirmed credits, two prior ambiguous reservations, 24 conservative usage, and 976 maximum authorized remaining. This is conservative internal accounting, not a provider-reported balance.

## Controller and credits

The controller is source-only, owner-configured, single-flight, market/holiday-aware, disabled by default, and has no browser, service-control, broker, or ledger route. It refuses a plan above 30 batch credits, three credits per instrument, or the supplied conservative remaining allowance. There are no automatic retries. Browser polling cannot invoke it.

The fixed 30-credit schedule means exactly three maximum observations per instrument: (1) opening/current evidence, (2) one bounded intraday mark, and (3) closing/post-market mark. If a required endpoint bundle cannot fit those three calls, the product set or schedule must be reduced before activation; the ceiling cannot expand.

## MU Tuesday template

MU remains `WAITING_FOR_CURRENT_TUESDAY_EVIDENCE` in `FORWARD_ONLY_UNADJUSTED_OBSERVATION` mode with a separate $10,000 synthetic sleeve basis. The template covers fundamental-dislocation/rebound research, long-horizon fundamental, catalyst/news reaction, and mean-reversion hypotheses. It requires current composite evidence, primary thesis evidence, liquidity, a governed cost model, immutable candidate identity, bear case, invalidation, committee review, and risk review. Entry, stop, target, size, position, return, and recommendation remain null.

## Rehearsal and handoff

The Monday rehearsal keeps the controller disabled and credits unchanged. The Tuesday fixture covers current/stale evidence, missing volume/adjustments/costs, candidate lineage, skeptic/committee/risk gates, synthetic observation, source failure, budget exhaustion, close, and post-close across all 24 rooms. Synthetic sleeves cannot create operational positions, orders, fills, transactions, broker calls, or ledger writes.

Opening-day reporting must list sources, metered requests, supported/blocked products, case transitions, synthetic activity, modeled costs and excursions, review decisions, failures, operational paper truth, authority, and next source wave. It must not claim profitability without authentic results.

## Provider-support follow-up

Before adjusted-history methods can activate, ask Financial Datasets to confirm whether `/prices` OHLCV is raw, split adjusted, dividend adjusted, or fully adjusted; how corporate actions are reflected; whether historical volume is adjusted for splits; and the recommended total-return treatment. No provider contact is made by this source batch, and waiting for that answer does not block the forward-only architecture.
