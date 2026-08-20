# E04 — Workflow and Orchestration

**Default priority:** P0
**Tickets:** 10

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T033 | P0 | Implement durable job repository | T032 |
| T034 | P0 | Implement worker lease mechanism | T033 |
| T035 | P0 | Implement bounded retry policy | T033,T014 |
| T036 | P0 | Implement transactional outbox | T032 |
| T037 | P0 | Implement outbox dispatcher | T036 |
| T038 | P0 | Implement consumer inbox idempotency | T032,T037 |
| T039 | P0 | Implement workflow run aggregate | T033 |
| T040 | P0 | Implement scheduler lease and schedule registry | T039 |
| T041 | P0 | Implement stand-down workflow propagation | T020,T039 |
| T042 | P0 | Implement controlled replay command | T033,T038 |
