# Local Development Setup

## Required Software

Install:

- Git;
- GitHub Desktop;
- Visual Studio Code;
- Docker Desktop;
- Python;
- Node.js;
- package manager for Node;
- optional PostgreSQL command-line client.

Use current supported stable releases compatible with the selected dependency locks.

## Verify

Run in a terminal:

```bash
git --version
docker --version
docker compose version
python --version
node --version
npm --version
```

## VS Code Extensions

Recommended:

- Python;
- Pylance;
- Docker;
- PostgreSQL/database client;
- ESLint;
- Prettier;
- GitHub integration;
- Markdown preview.

## Clone / Open Project

Open the root folder containing:

```text
ai-agents/
backend/
database/
docs/
frontend/
scripts/
tests/
```

## Python Virtual Environment

Recommended local workflow:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell equivalent:

```powershell
.venv\Scripts\Activate.ps1
```

## Node Dependencies

```bash
cd frontend
npm install
```

Exact package dependencies are added during bootstrap tickets.

## Docker

Docker Desktop must be running before local database/object-store startup.

## First Verification

Before implementation begins:

```text
Git clean
Docker working
Python working
Node working
VS Code open at project root
```
