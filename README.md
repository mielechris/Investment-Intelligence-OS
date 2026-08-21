# Investment-Intelligence-OS

## Verification

GitHub Actions runs the repository's automated verification on feature branches and pull requests via `.github/workflows/ci.yml`:

- Frontend: `npm ci`, TypeScript/Vite build, ESLint
- Backend: dependency install, `pytest -q`, V1.2 FastAPI import check

PRs remain draft until these checks are green.

## V1.2 persistence

The Interview-to-Agent Factory persists interviews, insight packets, agent definitions, and the live evidence inbox in SQLite instead of process memory.

- Default database: `BACK END/backend/data/iios.db`
- Override path with `IIOS_DB_PATH`
- Local database files are ignored by Git
- The repository layer preserves the existing factory API and is isolated so a future Postgres migration does not require rewriting the frontend or factory routes

## IPO Intelligence Agent

V1.2 includes a persistent, approved system agent dedicated to newly filed and newly listed U.S. IPOs.

- Primary source: SEC EDGAR latest-filings feed
- Tracks `S-1`, `S-1/A`, `F-1`, `F-1/A`, `EFFECT`, and `424B4`
- Live feed endpoint: `GET /intelligence/feeds/ipo/recent`
- Configure SEC access with `SEC_USER_AGENT`, for example `IIOS research contact@example.com`
- PAPER MODE only; no capital authority or live execution

## Market History & Regime Analyst

V1.2 also seeds an approved historical specialist that studies why markets moved in prior episodes and whether a current setup is genuinely analogous.

The agent must:

- separate causal mechanisms from simple correlation
- identify the regime, catalyst, expectations, liquidity/positioning, and cross-asset reaction
- distinguish what was known ex ante from hindsight
- include counterexamples and structural breaks
- score regime similarity instead of assuming history repeats
- never use one historical analog as sufficient trade justification

Historical equity endpoint: `GET /intelligence/feeds/history/equity/{symbol}`.

Configure `ALPHAVANTAGE_API_KEY` to enable equity daily OHLCV and historical series. Alpha Vantage `TIME_SERIES_DAILY` is used for this layer; `compact` returns the latest 100 daily observations and `full` can be requested when the provider entitlement supports it.

## Continuous intelligence ingestion

When the V1.2 FastAPI app starts, IIOS launches a background ingestion loop that continuously pulls configured feeds and stores normalized, deduplicated evidence in SQLite.

Default cadence:

- Crypto observations: every 60 seconds
- SEC IPO filings: every 300 seconds
- SEC company filings (`8-K`, `10-Q`, `10-K`, Form `4`): every 300 seconds
- Equity/ETF daily bars for configured symbols: every 900 seconds when `ALPHAVANTAGE_API_KEY` is configured
- FRED macro series: every 1,800 seconds when `FRED_API_KEY` is configured

Configuration:

- `IIOS_CRYPTO_INTERVAL_SECONDS`
- `IIOS_SEC_IPO_INTERVAL_SECONDS`
- `IIOS_SEC_COMPANY_INTERVAL_SECONDS`
- `IIOS_EQUITY_INTERVAL_SECONDS`
- `IIOS_FRED_INTERVAL_SECONDS`
- `IIOS_CRYPTO_ASSETS` (default `bitcoin,ethereum`)
- `IIOS_EQUITY_SYMBOLS` (default `SPY,QQQ,IWM,DIA,AAPL,MSFT,NVDA,AMZN,META`)
- `IIOS_FRED_SERIES` (expanded default covers rates, inflation, labor, yield curves, VIX, dollar, and oil)

Operations endpoints:

- `GET /intelligence/feeds/status` — provider and ingestion health
- `GET /intelligence/feeds/inbox` — persisted evidence inbox
- `POST /intelligence/feeds/ingestion/run-now` — force an immediate ingestion cycle
- `GET /intelligence/feeds/company/recent` — recent SEC company filings
- `GET /intelligence/feeds/market/equity/{symbol}` — latest equity daily bar
- `GET /intelligence/feeds/history/equity/{symbol}` — historical daily equity series

The current loop is designed for a single always-on IIOS instance. A true 24/7 production deployment requires the backend process itself to stay running on a server/container host. The persistence and provider interfaces are separated so the scheduler can later move to dedicated workers with Postgres/Redis without changing agent APIs.
