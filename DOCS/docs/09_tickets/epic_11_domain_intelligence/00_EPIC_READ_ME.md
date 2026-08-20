# E11 — Domain Intelligence

**Default priority:** P1
**Tickets:** 12

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T113 | P1 | Implement market regime engine V0.1 | T062,T102 |
| T114 | P1 | Implement sector state builder | T028,T055,T113 |
| T115 | P1 | Implement supply-chain relationship importer | T060 |
| T116 | P1 | Implement weather observation adapter and normalizer | T044,T048 |
| T117 | P1 | Implement crop and agricultural state builder | T116,T028 |
| T118 | P1 | Implement livestock disease state builder | T054,T028 |
| T119 | P1 | Implement commodity state and futures-curve builder | T055,T117,T118 |
| T120 | P1 | Implement geopolitical event state builder | T054,T028 |
| T121 | P1 | Implement corporate relationship mapping pipeline | T028,T064 |
| T122 | P1 | Implement institutional flow normalization | T044,T048,T055 |
| T123 | P1 | Implement domain event materiality ranking | T114,T117,T119,T120 |
| T124 | P1 | Implement domain intelligence read models | T113,T114,T117,T119,T120,T121 |
