# Investment-Intelligence-OS

## Verification

GitHub Actions runs the repository's automated verification on feature branches and pull requests via `.github/workflows/ci.yml`:

- Frontend: `npm ci`, TypeScript/Vite build, ESLint
- Backend: dependency install, `pytest -q`, V1.2 FastAPI import check

PRs remain draft until these checks are green.

## V1.2 persistence

The Interview-to-Agent Factory now persists interviews, insight packets, agent definitions, and the live evidence inbox in SQLite instead of process memory.

- Default database: `BACK END/backend/data/iios.db`
- Override path with `IIOS_DB_PATH`
- Local database files are ignored by Git
- The repository layer preserves the existing factory API and is intentionally isolated so a future Postgres migration does not require rewriting the frontend or factory routes

## IPO Intelligence Agent

V1.2 includes a persistent, approved system agent dedicated to newly filed and newly listed U.S. IPOs.

- Primary source: SEC EDGAR latest-filings feed
- Tracks IPO-related forms including `S-1`, `S-1/A`, `F-1`, `F-1/A`, `EFFECT`, and `424B4`
- Live feed endpoint: `GET /intelligence/feeds/ipo/recent`
- Configure compliant SEC access with `SEC_USER_AGENT`, for example `IIOS research contact@example.com`
- Agent remains PAPER MODE only and cannot authorize capital or execute live trades
- The agent evaluates business quality, financials, offering structure, dilution, insider selling, voting control, lockups, use of proceeds, red flags, valuation evidence, and missing information before escalating candidates to committee review

## Continuous intelligence ingestion

When the V1.2 FastAPI app starts, IIOS launches a background ingestion loop that continuously pulls configured feeds and stores normalized, deduplicated evidence in SQLite.

Default cadence:

- Crypto market observations: every 60 seconds
- SEC IPO filings: every 300 seconds
- FRED macro series: every 1,800 seconds when `FRED_API_KEY` is configured

Configuration:

- `IIOS_CRYPTO_INTERVAL_SECONDS`
- `IIOS_SEC_IPO_INTERVAL_SECONDS`
- `IIOS_FRED_INTERVAL_SECONDS`
- `IIOS_CRYPTO_ASSETS` (default `bitcoin,ethereum`)
- `IIOS_FRED_SERIES` (default `FEDFUNDS,CPIAUCSL,UNRATE,DGS2,DGS10,VIXCLS`)

Operations endpoints:

- `GET /intelligence/feeds/status` — provider and ingestion health
- `GET /intelligence/feeds/inbox` — persisted evidence inbox
- `POST /intelligence/feeds/ingestion/run-now` — force an immediate ingestion cycle

The current loop is designed for a single always-on IIOS instance. A true 24/7 production deployment still requires the backend process itself to run continuously on a server/container host. The persistence and provider interfaces are intentionally separated so the scheduler can later move to dedicated workers with Postgres/Redis without changing the agent APIs.
