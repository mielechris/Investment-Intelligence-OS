# Investment Intelligence OS
## Initial Repository Structure — v0.1

---

## 1. Target Repository

This structure aligns with the existing top-level folders while adding explicit ownership.

```text
investment-intelligence-os/
├── .github/
│   └── workflows/
├── ai-agents/
│   ├── agent_cards/
│   ├── prompts/
│   ├── evaluations/
│   └── README.md
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   └── iios/
│   │       ├── api/
│   │       ├── platform/
│   │       ├── identity/
│   │       ├── sources/
│   │       ├── ingestion/
│   │       ├── data_quality/
│   │       ├── market_data/
│   │       ├── knowledge/
│   │       ├── evidence/
│   │       ├── reasoning/
│   │       ├── agents/
│   │       ├── committee/
│   │       ├── portfolio/
│   │       ├── risk/
│   │       ├── execution/
│   │       ├── research/
│   │       ├── learning/
│   │       ├── reporting/
│   │       ├── workflow/
│   │       ├── audit/
│   │       └── infrastructure/
│   └── tests/
├── database/
│   ├── migrations/
│   ├── seeds/
│   ├── fixtures/
│   └── README.md
├── docs/
│   ├── 01_project_charter/
│   ├── 02_architecture/
│   ├── 03_specifications/
│   ├── 04_data_catalog/
│   ├── 05_agent_cards/
│   ├── 06_research/
│   ├── 07_operations/
│   ├── 08_decision_records/
│   ├── 09_tickets/
│   └── 10_implementation/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── api/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── pages/
│   │   ├── routes/
│   │   ├── state/
│   │   ├── types/
│   │   └── utils/
│   └── tests/
├── scripts/
│   ├── bootstrap/
│   ├── data/
│   ├── development/
│   ├── operations/
│   └── research/
├── tests/
│   ├── contract/
│   ├── end_to_end/
│   ├── fixtures/
│   ├── golden_trace/
│   ├── performance/
│   ├── reliability/
│   └── security/
├── artifacts/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── compose.yaml
├── Makefile
├── README.md
└── LICENSE-or-private-notice
```

---

## 2. Backend Module Structure

Each domain module should follow a consistent shape where useful:

```text
module_name/
├── domain/
│   ├── entities.py
│   ├── value_objects.py
│   ├── events.py
│   ├── policies.py
│   └── errors.py
├── application/
│   ├── commands.py
│   ├── queries.py
│   ├── handlers.py
│   └── ports.py
├── infrastructure/
│   ├── repositories.py
│   ├── models.py
│   └── adapters.py
└── api/
    ├── routes.py
    └── schemas.py
```

Not every small module needs every file.

---

## 3. Ownership Rules

### `ai-agents/`

Human-readable agent definitions, prompts, evaluation fixtures, and agent-specific documentation.

Runtime Python code still lives in `backend/src/iios/agents/`.

### `backend/`

Authoritative domain and application logic.

### `database/`

Migration environment, seeds, database-specific scripts, and schema fixtures.

ORM domain-specific models may remain near their backend module if the migration tool imports them.

### `docs/`

Governance, architecture, specs, catalog, agent cards, research, operations, decisions, tickets, and implementation guides.

### `frontend/`

Command-center interface only.

### `scripts/`

Operator and developer scripts. Scripts should call application interfaces rather than duplicate domain logic.

### `tests/`

Cross-module, contract, end-to-end, security, performance, and golden-trace tests.

---

## 4. Naming Rules

- folders: lowercase snake_case;
- Python modules: lowercase snake_case;
- Python classes: PascalCase;
- API paths: lowercase kebab-case or consistent resource names;
- environment variables: uppercase snake case;
- documentation packages: two-digit numeric prefix;
- tickets: `T###`;
- specifications: `SPEC-###`;
- ADRs: `ADR-ARCH-###` or assigned project convention;
- database constraints: explicit names.

---

## 5. Import Rules

Recommended dependency direction:

```text
domain
← application
← infrastructure and API
```

Domain code does not import infrastructure.

Cross-domain imports use application ports or shared stable value objects.

---

## 6. Generated Files

Generated artifacts include:

- OpenAPI schema;
- typed frontend API client;
- test reports;
- coverage;
- backtest artifacts;
- daily reports;
- database dumps.

Generated files are not hand-edited.

Large artifacts do not enter Git unless deliberately selected.

---

## 7. Environment Files

Commit:

- `.env.example`;
- typed configuration documentation;
- safe defaults.

Do not commit:

- `.env`;
- keys;
- tokens;
- passwords;
- broker credentials;
- private certificates.

---

## 8. Root Commands

The repository should provide simple commands for:

- bootstrap;
- start;
- stop;
- test;
- lint;
- typecheck;
- migrate;
- seed;
- run worker;
- run scheduler;
- run golden trace;
- backup;
- restore;
- generate API client.

Exact commands belong in Package 10 — Implementation.

---

## 9. Documentation Placement Rule

A document belongs in:

- Charter when it defines mission or governance;
- Architecture when it defines system structure and boundaries;
- Specifications when it defines exact required behavior;
- Data Catalog when it defines schemas and fields;
- Agent Cards when it defines an agent;
- Research when it defines tests and hypotheses;
- Operations when it defines how to run or recover;
- Decision Records when it records why a direction changed;
- Tickets when it defines implementation work;
- Implementation when it gives exact build instructions.

---

## 10. Repository Acceptance

- structure exists;
- all top-level folders have purpose;
- no duplicate authoritative docs;
- code imports respect boundaries;
- secrets are ignored;
- one command starts local dependencies;
- one command runs tests;
- architecture package lives at `docs/02_architecture/`;
- golden-trace fixtures have a stable home.
