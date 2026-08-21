# Investment-Intelligence-OS

## Verification

GitHub Actions runs the repository's automated verification on feature branches and pull requests via `.github/workflows/ci.yml`:

- Frontend: `npm ci`, TypeScript/Vite build, ESLint
- Backend: dependency install, `pytest -q`, V1.2 FastAPI import check

PRs remain draft until these checks are green.
