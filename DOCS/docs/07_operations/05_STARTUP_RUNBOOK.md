# Startup Runbook

## Pre-Startup

Verify:

- correct repository version;
- correct environment;
- secrets available;
- database reachable;
- object storage reachable;
- sufficient disk space;
- last backup status acceptable.

## Startup Sequence

1. Start PostgreSQL.
2. Start object storage.
3. Start optional cache.
4. Validate migrations.
5. Start API.
6. Start worker.
7. Start scheduler.
8. Start frontend.
9. Verify health endpoints.
10. Verify source registry.
11. Verify risk policy.
12. Verify paper execution adapter.
13. Verify PAPER environment banner.
14. Run smoke test.

## Critical Checks

System MUST NOT enter normal operation if:

- database schema is incompatible;
- risk policy missing;
- execution adapter is not paper-only;
- critical source permissions invalid;
- object storage unavailable for raw capture.

## Startup Completion

Record:

- release version;
- migration version;
- environment;
- process versions;
- health state;
- startup time.
