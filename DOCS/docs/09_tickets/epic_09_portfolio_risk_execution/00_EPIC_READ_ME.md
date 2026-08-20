# E09 — Portfolio Risk and Paper Execution

**Default priority:** P0
**Tickets:** 12

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T089 | P0 | Create initial paper portfolio and account service | T031 |
| T090 | P0 | Implement portfolio snapshot calculator | T089,T055 |
| T091 | P0 | Implement causal-cluster exposure mapper | T060,T090,T072 |
| T092 | P0 | Implement versioned risk-policy service | T031,T020 |
| T093 | P0 | Implement deterministic risk assessment | T092,T090,T091,T074 |
| T094 | P0 | Implement risk decision and approval expiry | T093 |
| T095 | P0 | Implement paper order-intent service | T094,T072,T088 |
| T096 | P0 | Implement paper execution adapter V0.1 | T095,T055 |
| T097 | P0 | Implement conservative fill model | T096 |
| T098 | P0 | Implement atomic paper accounting ledger | T031,T097 |
| T099 | P0 | Implement portfolio reconciliation service | T098 |
| T100 | P0 | Implement kill-switch enforcement | T020,T092,T099 |
