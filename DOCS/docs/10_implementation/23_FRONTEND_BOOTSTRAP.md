# Frontend Bootstrap

## Target

Typed React application.

## Suggested Structure

```text
frontend/src/
├── api/
├── app/
├── components/
├── features/
├── pages/
├── routes/
├── state/
├── types/
└── utils/
```

## Rules

Frontend may:

- render;
- filter;
- sort;
- request actions;
- hold temporary UI state.

Frontend may not own:

- positions;
- P&L;
- risk;
- source trust;
- order authorization.

## API Client

Generate or derive from OpenAPI.

## Server State

Use a server-state/query library or equivalent.

Requirements:

- caching;
- loading;
- errors;
- retries;
- polling/refetch;
- query invalidation.

## Global Banner

Always show:

```text
PAPER MODE
data cutoff
health
stand-down
release version
```

## First Page

Implement Today page before advanced visualization.
