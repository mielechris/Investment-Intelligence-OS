# Investment Intelligence OS
## Package 10 — Implementation — v0.1

**Destination:** `docs/10_implementation/`  
**Governing packages:** 01–09  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading only

---

## Purpose

This package turns the entire IIOS design into a practical build procedure.

It tells you:

- what to install;
- what files to create;
- what order to build in;
- how the backend is organized;
- how the database is created;
- how jobs and workflows run;
- how sources are ingested;
- how AI agents are wired;
- how the committee works;
- how risk blocks unsafe actions;
- how paper execution works;
- how research is run;
- how the frontend connects;
- how testing, CI, backup, release, and recovery work;
- what the first seven days should produce.

This package is the implementation bridge between the documentation and actual code.

---

## Implementation Rule

Build **one vertical slice** first.

Do not attempt to implement every connector, agent, asset class, or strategy simultaneously.

The first working chain is:

```text
source
→ raw record
→ canonical event
→ entity
→ evidence
→ causal chain
→ policy/macro/skeptic agents
→ committee
→ deterministic risk
→ paper order or no-trade
→ portfolio
→ journal
→ command center
→ postmortem
```

---

## Files

1. `01_IMPLEMENTATION_MASTER_PLAN.md`
2. `02_LOCAL_DEVELOPMENT_SETUP.md`
3. `03_ROOT_REPOSITORY_FILES.md`
4. `04_BACKEND_BOOTSTRAP.md`
5. `05_CONFIGURATION_AND_SECRETS.md`
6. `06_DATABASE_BOOTSTRAP.md`
7. `07_MIGRATION_IMPLEMENTATION.md`
8. `08_WORKFLOW_ENGINE_IMPLEMENTATION.md`
9. `09_INGESTION_PIPELINE_IMPLEMENTATION.md`
10. `10_FIRST_SOURCE_CONNECTORS.md`
11. `11_MARKET_DATA_ADAPTER.md`
12. `12_WORLD_MODEL_IMPLEMENTATION.md`
13. `13_EVIDENCE_AND_REASONING_IMPLEMENTATION.md`
14. `14_MODEL_GATEWAY_IMPLEMENTATION.md`
15. `15_AGENT_RUNTIME_IMPLEMENTATION.md`
16. `16_INITIAL_AGENTS_IMPLEMENTATION.md`
17. `17_INVESTMENT_COMMITTEE_IMPLEMENTATION.md`
18. `18_PORTFOLIO_AND_RISK_IMPLEMENTATION.md`
19. `19_PAPER_EXECUTION_IMPLEMENTATION.md`
20. `20_RESEARCH_ENGINE_IMPLEMENTATION.md`
21. `21_LEARNING_AND_POSTMORTEM_IMPLEMENTATION.md`
22. `22_API_IMPLEMENTATION.md`
23. `23_FRONTEND_BOOTSTRAP.md`
24. `24_COMMAND_CENTER_IMPLEMENTATION.md`
25. `25_OBSERVABILITY_IMPLEMENTATION.md`
26. `26_BACKUP_AND_RECOVERY_IMPLEMENTATION.md`
27. `27_SECURITY_IMPLEMENTATION.md`
28. `28_TESTING_IMPLEMENTATION.md`
29. `29_CI_AND_RELEASE_IMPLEMENTATION.md`
30. `30_GOLDEN_TRACE_IMPLEMENTATION.md`
31. `31_SEVEN_DAY_BUILD_SEQUENCE.md`
32. `32_FIRST_FOUR_WEEKS.md`
33. `33_DEVELOPER_COMMAND_REFERENCE.md`
34. `34_IMPLEMENTATION_ACCEPTANCE_CHECKLIST.md`
35. `35_IMPLEMENTATION_SESSION_TEMPLATE.md`

---

## Package 10 Is Not Permission to Skip Packages 01–09

When a coding decision conflicts with:

- Constitution;
- Architecture;
- Specification;
- Data Catalog;
- Agent Card;
- Research Standard;
- Operations Runbook;
- ADR;
- Ticket;

the higher-level governing document wins unless it is formally superseded.

---

## Recommended Workflow

For every ticket:

```text
open ticket
→ read linked spec
→ read linked architecture
→ implement smallest correct change
→ add tests
→ run tests
→ update docs if needed
→ commit with T###
→ move ticket to DONE
```
