# Investment Intelligence OS
## Package 04 — Data Catalog — v0.1

**Destination:** `docs/04_data_catalog/`  
**Governing packages:** `01_project_charter`, `02_architecture`, `03_specifications`  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading only

---

## Purpose

This package defines the canonical data language of IIOS.

It specifies:

- canonical objects;
- identifiers;
- field meanings;
- timestamps;
- state vocabularies;
- provenance;
- lineage;
- PostgreSQL ownership;
- quality metadata;
- point-in-time rules;
- retention;
- schema evolution.

The Data Catalog defines **what data means**. Package 10 will define the exact implementation code.

---

## Catalog Files

1. `01_CATALOG_CONVENTIONS.md`
2. `02_TIME_AND_POINT_IN_TIME_SEMANTICS.md`
3. `03_ENUMS_AND_STATUS_VOCABULARY.md`
4. `04_SOURCE_AND_RIGHTS_CATALOG.md`
5. `05_INGESTION_AND_RAW_RECORDS.md`
6. `06_CANONICAL_EVENT_SCHEMA.md`
7. `07_ENTITY_AND_IDENTITY_SCHEMA.md`
8. `08_RELATIONSHIP_AND_WORLD_STATE_SCHEMA.md`
9. `09_INSTRUMENT_AND_MARKET_REFERENCE_SCHEMA.md`
10. `10_MARKET_DATA_SCHEMA.md`
11. `11_EVIDENCE_AND_CLAIM_SCHEMA.md`
12. `12_CAUSAL_CHAIN_SCHEMA.md`
13. `13_HYPOTHESIS_AND_THESIS_SCHEMA.md`
14. `14_AGENT_MODEL_AND_PROMPT_SCHEMA.md`
15. `15_COMMITTEE_AND_DECISION_SCHEMA.md`
16. `16_PORTFOLIO_AND_POSITION_SCHEMA.md`
17. `17_RISK_SCHEMA.md`
18. `18_ORDER_FILL_AND_EXECUTION_SCHEMA.md`
19. `19_RESEARCH_DATASET_AND_STRATEGY_SCHEMA.md`
20. `20_RESEARCH_RUN_AND_RESULT_SCHEMA.md`
21. `21_JOURNAL_MEMORY_AND_LEARNING_SCHEMA.md`
22. `22_WORKFLOW_JOB_AND_EVENT_SCHEMA.md`
23. `23_AUDIT_INCIDENT_AND_RELEASE_SCHEMA.md`
24. `24_DATA_QUALITY_AND_TRUST_SCHEMA.md`
25. `25_DOMAIN_INTELLIGENCE_EXTENSIONS.md`
26. `26_DATABASE_SCHEMA_OWNERSHIP_MAP.md`
27. `27_KEYS_CONSTRAINTS_AND_INDEXING.md`
28. `28_RETENTION_LINEAGE_AND_DELETION.md`
29. `29_SCHEMA_VERSIONING_AND_MIGRATION.md`
30. `30_DATA_CATALOG_ACCEPTANCE_CHECKLIST.md`
31. `31_FIELD_DICTIONARY_TEMPLATE.md`

---

## Global Data Rules

Every durable canonical object MUST:

1. have a stable opaque identifier;
2. carry a schema version;
3. use timezone-aware timestamps;
4. preserve provenance when derived from external information;
5. preserve environment;
6. preserve historical versions rather than overwrite material history;
7. distinguish unknown from zero;
8. preserve units and currencies explicitly;
9. be traceable through correlation and causation IDs where operational;
10. support audit reconstruction.

---

## PostgreSQL Logical Schemas

```text
platform
source
ingest
market
knowledge
evidence
reasoning
agents
decision
portfolio
risk
execution
research
learning
workflow
audit
```

Only the owning module may perform authoritative writes to its tables.
