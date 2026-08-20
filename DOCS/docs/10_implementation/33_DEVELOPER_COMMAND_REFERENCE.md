# Developer Command Reference

Exact implementation may use Make, task runner, shell scripts, or package scripts.

The repository should converge on commands equivalent to:

## Bootstrap

```bash
make bootstrap
```

## Start Dependencies

```bash
make infra-up
```

## Start Backend API

```bash
make api
```

## Start Worker

```bash
make worker
```

## Start Scheduler

```bash
make scheduler
```

## Start Frontend

```bash
make frontend
```

## Run All Tests

```bash
make test
```

## Backend Tests

```bash
make test-backend
```

## Frontend Tests

```bash
make test-frontend
```

## Lint

```bash
make lint
```

## Type Check

```bash
make typecheck
```

## Migrate

```bash
make migrate
```

## Golden Trace

```bash
make golden-trace
```

## Backup

```bash
make backup
```

## Restore to Test

```bash
make restore-test BACKUP=...
```

## Stop

```bash
make down
```

## Rule

The actual commands implemented in the repository become the source of truth once Package 10 tickets are completed.
