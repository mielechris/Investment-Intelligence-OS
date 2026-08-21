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
