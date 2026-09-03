# Cross-asset provider evaluation — Superbatch 6

Status: evaluation only. No account, credential, package, paid plan, or network adapter is activated. Current cost is **$0**.

| Need | Candidate names and capabilities | Point-in-time / provenance | Licensing and cost control | Status |
|---|---|---|---|---|
| Equities / ETFs | Massive: US prices, reference data and corporate actions; Intrinio: prices, ETF holdings/metadata | Require exchange/source timestamps, delisted universe, corrections and as-of queries | Massive lists individual tiers from free EOD through paid delayed/real-time; individual use restrictions require review. Intrinio business pricing is quote-based | NOT_ACTIVATED |
| Fundamentals | SEC EDGAR APIs for primary filings/XBRL; Intrinio standardized and as-reported fundamentals | Preserve filing acceptance time, amendments and original accession | SEC fair-access policy required; Intrinio licensing/price requires quote | NOT_ACTIVATED |
| IPO / new listings | SEC registration filings; Intrinio IPO metadata | Registration/offer/listing events must be separately timestamped | Public filing reuse and commercial metadata rights require legal review | NOT_ACTIVATED |
| Treasuries / bonds | US Treasury Fiscal Data and Treasury publications; FRED macro/rate series; commercial fixed-income vendor TBD | Observation/release/vintage dates mandatory; evaluated price provenance unresolved | Public-data terms review; evaluated bond pricing remains unknown | NOT_ACTIVATED |
| Commodities / futures | Databento and Massive futures datasets; direct CME/ICE terms | Contract master, expiry, roll, corrections and venue timestamps mandatory | Databento usage/license fees vary by dataset and bytes; exchange fees and redistribution rights apply | NOT_ACTIVATED |
| Macroeconomic | FRED/ALFRED and official statistical agencies | Use vintage/release dates; ALFRED-style revision history required | Public terms and per-series redistribution review | NOT_ACTIVATED |
| Transcripts / news | Issuer publications, SEC exhibits, licensed vendors such as Intrinio/NewsEdge | Publisher, publication time, correction and rights metadata required | Full-text and redistribution rights are not assumed; quote pricing unknown | NOT_ACTIVATED |
| Historical intraday | Databento, Massive, direct venue data | Corporate actions, symbology history, survivorship and corrections required | Hard byte/request/month ceilings required before any trial or paid use | NOT_ACTIVATED |

Official references reviewed: Massive pricing and stock coverage (`https://massive.com/pricing`, `https://massive.com/stocks`); Databento pricing/licensing (`https://databento.com/pricing/`); Intrinio pricing/data feeds (`https://intrinio.com/pricing`, `https://intrinio.com/data-feeds`); SEC EDGAR APIs (`https://www.sec.gov/search-filings/edgar-application-programming-interfaces`).

## Activation requirements

Before selection, obtain written answers for provenance, point-in-time semantics, personal paper-research/display rights, retention, redistribution, outage behavior, correction delivery, corporate actions, coverage, rate limits, historical depth, and deletion. Enforce per-request, daily, and monthly hard ceilings with fail-closed exhaustion. Trial credits are not a budget control. Unknown pricing or licensing remains `NOT_ACTIVATED`.
