# E12 — API and Frontend Command Center

**Default priority:** P0/P1
**Tickets:** 10

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T125 | P0 | Create FastAPI application and health endpoints | T005,T011,T021 |
| T126 | P0 | Implement API authentication and authorization middleware | T017,T125 |
| T127 | P0 | Implement canonical API error responses | T014,T125 |
| T128 | P0 | Implement source event evidence and world-state query endpoints | T043,T061,T064,T062,T125 |
| T129 | P0 | Implement hypothesis thesis and committee endpoints | T071,T072,T087,T125 |
| T130 | P0 | Implement portfolio risk order and journal endpoints | T090,T094,T095,T099,T111,T125 |
| T131 | P0 | Generate typed frontend API client | T125,T126,T127,T128,T129,T130 |
| T132 | P0 | Build Today command-center page | T006,T131,T128,T130 |
| T133 | P0/P1 | Build decision detail and explainability page | T076,T131,T129 |
| T134 | P1 | Build portfolio risk research and system-health pages | T131,T130,T111 |
