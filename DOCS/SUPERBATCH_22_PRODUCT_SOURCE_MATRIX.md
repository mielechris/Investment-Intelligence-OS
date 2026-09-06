# Product and Source Activation Matrix

All rows begin `NOT_ACTIVATED`. Activation requires rights/licensing review, point-in-time provenance, family-complete evidence, freshness, liquidity, costs, invalidation, human review, and an independently approved operational procedure.

| Products | Count | Evidence family | Special blocker |
|---|---:|---|---|
| U.S./international/emerging equities and equity ETFs | 7 | Equity/ETF | Exchange, corporate action, liquidity, cost and session evidence |
| Treasury bills, notes/bonds and duration proxies | 3 | Treasury or explicit proxy | Yield convention, maturity, duration, convexity and settlement |
| Investment-grade, high-yield and municipal credit | 3 | Credit | Quality, callable terms, tax basis and quote convention |
| Equity/ETF and index options | 2 | Options | Synchronized quotes, Greeks, multiplier and maximum loss; otherwise `RESEARCH_ONLY_UNPRICEABLE` |
| Commodity proxies and futures references | 2 | Commodity | Exposure basis, expiry, roll, carry and licensing |
| FX spot references and listed proxies | 2 | FX | Pair, session, spread, carry, rollover and proxy tracking |
| Crypto references and listed proxies | 2 | Crypto | Venue/reference, custody/structure warning, weekend and proxy basis |
| REITs, preferred/income and money-market products | 3 | Income | Distribution basis, duration/rate sensitivity, liquidity and redemption terms |

No proxy is treated as its underlying. Reference-only products cannot create orders. Registration alone never makes a desk current, research eligible, or paper eligible.
