# Root Repository Files

Create or verify these files:

```text
.env.example
.gitignore
compose.yaml
Makefile
README.md
```

## `.gitignore`

Must exclude at minimum:

```gitignore
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
node_modules/
dist/
build/
coverage/
.coverage
.DS_Store
*.db
*.sqlite*
artifacts/*
!artifacts/.gitkeep
data/
raw/
backups/
```

Adjust as project dependencies evolve.

## `.env.example`

Use placeholders only:

```dotenv
IIOS_ENVIRONMENT=PAPER
IIOS_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/iios
IIOS_OBJECT_STORE_ENDPOINT=http://localhost:9000
IIOS_OBJECT_STORE_BUCKET=iios-paper
IIOS_OBJECT_STORE_ACCESS_KEY=CHANGE_ME
IIOS_OBJECT_STORE_SECRET_KEY=CHANGE_ME
IIOS_MODEL_PROVIDER_KEY=CHANGE_ME
IIOS_PAPER_BROKER_MODE=internal
IIOS_LOG_LEVEL=INFO
```

Never put real credentials in this file.

## `compose.yaml`

Initial services:

```yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: iios
      POSTGRES_USER: iios
      POSTGRES_PASSWORD: local_dev_only
    ports:
      - "5432:5432"
    volumes:
      - iios_pgdata:/var/lib/postgresql/data

  object_store:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: local_dev
      MINIO_ROOT_PASSWORD: local_dev_change_me
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - iios_objects:/data

volumes:
  iios_pgdata:
  iios_objects:
```

Production-quality secrets must not use these development values.

## Root README

Include:

- mission;
- paper-only boundary;
- quick start;
- docs links;
- test command;
- current release;
- warning that live trading is disabled.
