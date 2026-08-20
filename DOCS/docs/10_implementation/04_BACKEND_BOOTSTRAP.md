# Backend Bootstrap

## Target Layout

```text
backend/
├── pyproject.toml
├── src/
│   └── iios/
│       ├── __init__.py
│       ├── api/
│       ├── platform/
│       ├── identity/
│       ├── sources/
│       ├── ingestion/
│       ├── data_quality/
│       ├── market_data/
│       ├── knowledge/
│       ├── evidence/
│       ├── reasoning/
│       ├── agents/
│       ├── committee/
│       ├── portfolio/
│       ├── risk/
│       ├── execution/
│       ├── research/
│       ├── learning/
│       ├── workflow/
│       ├── audit/
│       └── infrastructure/
└── tests/
```

## `pyproject.toml`

Use one canonical dependency file.

Initial dependency classes:

- FastAPI;
- ASGI server;
- Pydantic/settings;
- SQLAlchemy;
- PostgreSQL driver;
- Alembic;
- HTTP client;
- object-store SDK;
- numerical/data libraries;
- testing;
- lint/type tooling.

Exact versions must be locked.

## Application Entrypoints

Create:

```text
iios.api.main
iios.workflow.worker_main
iios.workflow.scheduler_main
```

Each process loads:

- typed settings;
- environment guard;
- logging;
- database;
- health registry.

## Dependency Direction

Domain code must not import:

- FastAPI;
- provider SDKs;
- frontend;
- global database session;
- model-provider SDKs.

Infrastructure adapters depend inward on application ports.

## First Test

```python
def test_package_imports():
    import iios
```

Then test each process entrypoint can initialize in TEST mode without external internet access.
