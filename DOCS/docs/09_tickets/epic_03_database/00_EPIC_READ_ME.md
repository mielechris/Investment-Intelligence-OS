# E03 — Database and Core Data Model

**Default priority:** P0
**Tickets:** 12

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T021 | P0 | Create PostgreSQL development container | T007,T011 |
| T022 | P0 | Initialize migration framework | T021 |
| T023 | P0 | Create PostgreSQL logical schemas | T022 |
| T024 | P0 | Enable required PostgreSQL extensions | T022 |
| T025 | P0 | Implement common database metadata mixins | T005,T023 |
| T026 | P0 | Create source registry tables | T023,T025,T019 |
| T027 | P0 | Create ingestion and raw-record tables | T026 |
| T028 | P0 | Create canonical event and entity tables | T023,T025 |
| T029 | P0 | Create evidence and reasoning tables | T028 |
| T030 | P0 | Create agent committee and model registry tables | T023,T025 |
| T031 | P0 | Create portfolio risk and paper execution tables | T023,T025 |
| T032 | P0 | Create workflow research learning and audit tables | T023,T025 |
