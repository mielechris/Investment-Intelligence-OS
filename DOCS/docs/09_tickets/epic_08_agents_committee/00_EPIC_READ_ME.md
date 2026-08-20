# E08 — AI Agent Runtime and Committee

**Default priority:** P0
**Tickets:** 12

| Ticket | Priority | Title | Dependencies |
|---|---|---|---|
| T077 | P0 | Implement model provider protocol and gateway skeleton | T011,T030 |
| T078 | P0 | Implement model registry service | T030,T077 |
| T079 | P0 | Implement prompt registry service | T030 |
| T080 | P0 | Implement governed retrieval builder | T063,T050,T019 |
| T081 | P0 | Implement agent definition and tool-allowlist service | T030,T077 |
| T082 | P0 | Implement structured agent-run executor | T077,T080,T081 |
| T083 | P0 | Implement prompt-injection defense tests and delimiters | T080,T082 |
| T084 | P0 | Implement Policy Analyst V0.1 | T082,T061,T076 |
| T085 | P0 | Implement Macro and Rates Analyst V0.1 | T082,T062,T076 |
| T086 | P0 | Implement Skeptic / Red Team V0.1 | T082,T076 |
| T087 | P0 | Implement committee session and bounded debate service | T030,T084,T085,T086 |
| T088 | P0 | Implement committee decision expiry and reevaluation triggers | T087,T066 |
