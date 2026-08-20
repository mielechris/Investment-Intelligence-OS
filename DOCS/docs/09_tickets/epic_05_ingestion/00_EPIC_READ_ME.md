# E05 — Source Registry and Ingestion

**Default priority:** P0
**Tickets:** 14

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T043 | P0 | Implement source registry application service | T026,T019 |
| T044 | P0 | Define connector protocol and source item contract | T043 |
| T045 | P0 | Implement immutable object-storage adapter | T007,T011 |
| T046 | P0 | Implement raw-record capture service | T027,T044,T045 |
| T047 | P0 | Implement parser protocol and registry | T046 |
| T048 | P0 | Implement canonical normalizer protocol | T047 |
| T049 | P0 | Implement source deduplication and revision detection | T046,T048 |
| T050 | P0 | Implement source freshness and health calculator | T043,T049 |
| T051 | P0 | Implement quarantine workflow | T019,T027,T050 |
| T052 | P0 | Create official presidential/policy connector | T044,T046,T047,T048 |
| T053 | P0 | Create Federal Reserve/macro connector | T044,T046,T047,T048 |
| T054 | P0 | Create non-policy official connector | T044,T046,T047,T048 |
| T055 | P0 | Implement initial market-data adapter interface | T044 |
| T056 | P0 | Build end-to-end ingestion workflow for three source domains | T052,T053,T054,T055,T042 |
