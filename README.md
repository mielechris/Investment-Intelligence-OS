# Investment-Intelligence-OS

## Verification

GitHub Actions runs the repository's automated verification on feature branches and pull requests via `.github/workflows/ci.yml`:

- Frontend: `npm ci`, TypeScript/Vite build, ESLint
- Backend: dependency install, `pytest -q`, V1.2 FastAPI import check

PRs remain draft until these checks are green.

## V1.2 persistence

The Interview-to-Agent Factory now persists interviews, insight packets, and agent definitions in SQLite instead of process memory.

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
