# Master Ticket Backlog

**Total implementation tickets:** 168

| Ticket | Epic | Priority | Title | Dependencies | Specs |
|---|---|---|---|---|---|
| T001 | E01 | P0 | Create repository baseline and root README | — | SPEC-000,SPEC-015 |
| T002 | E01 | P0 | Create canonical repository directory structure | T001 | SPEC-015 |
| T003 | E01 | P0 | Add root .gitignore and artifact exclusions | T001 | SPEC-013,SPEC-015 |
| T004 | E01 | P0 | Add safe .env.example | T003 | SPEC-013,SPEC-015 |
| T005 | E01 | P0 | Bootstrap Python backend package | T002 | SPEC-012,SPEC-015 |
| T006 | E01 | P0 | Bootstrap frontend TypeScript application | T002 | SPEC-011,SPEC-012 |
| T007 | E01 | P0 | Create root developer command interface | T005,T006 | SPEC-015 |
| T008 | E01 | P1 | Add project version module | T005 | SPEC-015 |
| T009 | E01 | P1 | Add architecture dependency-lint rule skeleton | T005 | SPEC-000,SPEC-015 |
| T010 | E01 | P0 | Create golden-trace fixture directory and manifest skeleton | T002 | SPEC-000,SPEC-015 |
| T011 | E02 | P0 | Implement typed application settings | T005,T004 | SPEC-013,SPEC-015 |
| T012 | E02 | P0 | Implement explicit environment mode guard | T011 | SPEC-000,SPEC-013,SPEC-015 |
| T013 | E02 | P0 | Implement correlation and causation context | T005 | SPEC-013,SPEC-016 |
| T014 | E02 | P0 | Implement common error taxonomy | T005 | SPEC-012,SPEC-013,SPEC-016 |
| T015 | E02 | P0 | Implement secret-loading abstraction | T011 | SPEC-013,SPEC-015 |
| T016 | E02 | P0 | Add automated secret scanning configuration | T003 | SPEC-013 |
| T017 | E02 | P0 | Implement authenticated owner identity skeleton | T011 | SPEC-012,SPEC-013 |
| T018 | E02 | P1 | Implement service identity model | T017 | SPEC-013 |
| T019 | E02 | P0 | Create information-rights enforcement interface | T011 | SPEC-000,SPEC-013,SPEC-018 |
| T020 | E02 | P0 | Implement security stand-down trigger interface | T012,T014 | SPEC-013,SPEC-015 |
| T021 | E03 | P0 | Create PostgreSQL development container | T007,T011 | SPEC-015 |
| T022 | E03 | P0 | Initialize migration framework | T021 | SPEC-015 |
| T023 | E03 | P0 | Create PostgreSQL logical schemas | T022 | SPEC-001,SPEC-002,SPEC-003,SPEC-007,SPEC-009,SPEC-016 |
| T024 | E03 | P0 | Enable required PostgreSQL extensions | T022 | SPEC-002,SPEC-003 |
| T025 | E03 | P0 | Implement common database metadata mixins | T005,T023 | SPEC-001,SPEC-013 |
| T026 | E03 | P0 | Create source registry tables | T023,T025,T019 | SPEC-001,SPEC-018 |
| T027 | E03 | P0 | Create ingestion and raw-record tables | T026 | SPEC-001,SPEC-018 |
| T028 | E03 | P0 | Create canonical event and entity tables | T023,T025 | SPEC-001,SPEC-002 |
| T029 | E03 | P0 | Create evidence and reasoning tables | T028 | SPEC-003,SPEC-004,SPEC-017 |
| T030 | E03 | P0 | Create agent committee and model registry tables | T023,T025 | SPEC-005,SPEC-006,SPEC-014 |
| T031 | E03 | P0 | Create portfolio risk and paper execution tables | T023,T025 | SPEC-007,SPEC-009 |
| T032 | E03 | P0 | Create workflow research learning and audit tables | T023,T025 | SPEC-008,SPEC-010,SPEC-016 |
| T033 | E04 | P0 | Implement durable job repository | T032 | SPEC-016 |
| T034 | E04 | P0 | Implement worker lease mechanism | T033 | SPEC-016 |
| T035 | E04 | P0 | Implement bounded retry policy | T033,T014 | SPEC-016 |
| T036 | E04 | P0 | Implement transactional outbox | T032 | SPEC-016 |
| T037 | E04 | P0 | Implement outbox dispatcher | T036 | SPEC-016 |
| T038 | E04 | P0 | Implement consumer inbox idempotency | T032,T037 | SPEC-016 |
| T039 | E04 | P0 | Implement workflow run aggregate | T033 | SPEC-016 |
| T040 | E04 | P0 | Implement scheduler lease and schedule registry | T039 | SPEC-016 |
| T041 | E04 | P0 | Implement stand-down workflow propagation | T020,T039 | SPEC-016,SPEC-007 |
| T042 | E04 | P0 | Implement controlled replay command | T033,T038 | SPEC-001,SPEC-016 |
| T043 | E05 | P0 | Implement source registry application service | T026,T019 | SPEC-001,SPEC-018 |
| T044 | E05 | P0 | Define connector protocol and source item contract | T043 | SPEC-001,SPEC-012 |
| T045 | E05 | P0 | Implement immutable object-storage adapter | T007,T011 | SPEC-001,SPEC-015 |
| T046 | E05 | P0 | Implement raw-record capture service | T027,T044,T045 | SPEC-001 |
| T047 | E05 | P0 | Implement parser protocol and registry | T046 | SPEC-001 |
| T048 | E05 | P0 | Implement canonical normalizer protocol | T047 | SPEC-001 |
| T049 | E05 | P0 | Implement source deduplication and revision detection | T046,T048 | SPEC-001 |
| T050 | E05 | P0 | Implement source freshness and health calculator | T043,T049 | SPEC-018 |
| T051 | E05 | P0 | Implement quarantine workflow | T019,T027,T050 | SPEC-001,SPEC-013,SPEC-018 |
| T052 | E05 | P0 | Create official presidential/policy connector | T044,T046,T047,T048 | SPEC-001,SPEC-025 |
| T053 | E05 | P0 | Create Federal Reserve/macro connector | T044,T046,T047,T048 | SPEC-001,SPEC-021 |
| T054 | E05 | P0 | Create non-policy official connector | T044,T046,T047,T048 | SPEC-001 |
| T055 | E05 | P0 | Implement initial market-data adapter interface | T044 | SPEC-001,SPEC-012 |
| T056 | E05 | P0 | Build end-to-end ingestion workflow for three source domains | T052,T053,T054,T055,T042 | SPEC-001,SPEC-016 |
| T057 | E06 | P0 | Implement entity registry repository and service | T028 | SPEC-002 |
| T058 | E06 | P0 | Implement entity resolution pipeline | T057 | SPEC-002 |
| T059 | E06 | P1 | Implement entity merge/split audit operations | T057 | SPEC-002 |
| T060 | E06 | P0 | Implement entity relationship service | T057,T058 | SPEC-002,SPEC-027 |
| T061 | E06 | P0 | Implement policy lifecycle state projector | T028,T056,T060 | SPEC-002 |
| T062 | E06 | P0 | Implement world-state snapshot builder | T057,T060,T050 | SPEC-002,SPEC-021 |
| T063 | E06 | P0 | Implement evidence object creation service | T029,T028 | SPEC-003 |
| T064 | E06 | P0 | Implement claim and evidence-link service | T063 | SPEC-003 |
| T065 | E06 | P1 | Implement evidence deduplication and independence clustering | T063,T050 | SPEC-003,SPEC-018 |
| T066 | E06 | P0 | Implement evidence retraction propagation | T064 | SPEC-003 |
| T067 | E07 | P0 | Implement causal-chain domain model and service | T029,T064 | SPEC-004 |
| T068 | E07 | P0 | Implement counter-chain service | T067 | SPEC-004 |
| T069 | E07 | P0 | Implement assumptions and falsifiers | T067 | SPEC-004,SPEC-017 |
| T070 | E07 | P0 | Implement missing-information request queue | T067 | SPEC-004 |
| T071 | E07 | P0 | Implement hypothesis registry service | T029,T067,T068,T069 | SPEC-017 |
| T072 | E07 | P0 | Implement thesis construction service | T071 | SPEC-017,SPEC-029 |
| T073 | E07 | P1 | Implement historical analog query service | T062,T067 | SPEC-004,SPEC-021 |
| T074 | E07 | P0 | Implement thesis hard-gate validator | T072,T063,T068 | SPEC-000,SPEC-029 |
| T075 | E07 | P0/P1 | Implement thesis scoring dimensions | T072,T050,T062 | SPEC-029 |
| T076 | E07 | P0 | Implement explainability packet builder | T064,T067,T068,T071,T072 | SPEC-020 |
| T077 | E08 | P0 | Implement model provider protocol and gateway skeleton | T011,T030 | SPEC-005,SPEC-014 |
| T078 | E08 | P0 | Implement model registry service | T030,T077 | SPEC-014 |
| T079 | E08 | P0 | Implement prompt registry service | T030 | SPEC-014 |
| T080 | E08 | P0 | Implement governed retrieval builder | T063,T050,T019 | SPEC-005,SPEC-013 |
| T081 | E08 | P0 | Implement agent definition and tool-allowlist service | T030,T077 | SPEC-005 |
| T082 | E08 | P0 | Implement structured agent-run executor | T077,T080,T081 | SPEC-005 |
| T083 | E08 | P0 | Implement prompt-injection defense tests and delimiters | T080,T082 | SPEC-005,SPEC-013 |
| T084 | E08 | P0 | Implement Policy Analyst V0.1 | T082,T061,T076 | SPEC-005 |
| T085 | E08 | P0 | Implement Macro and Rates Analyst V0.1 | T082,T062,T076 | SPEC-005 |
| T086 | E08 | P0 | Implement Skeptic / Red Team V0.1 | T082,T076 | SPEC-005 |
| T087 | E08 | P0 | Implement committee session and bounded debate service | T030,T084,T085,T086 | SPEC-006 |
| T088 | E08 | P0 | Implement committee decision expiry and reevaluation triggers | T087,T066 | SPEC-006 |
| T089 | E09 | P0 | Create initial paper portfolio and account service | T031 | SPEC-007,SPEC-009 |
| T090 | E09 | P0 | Implement portfolio snapshot calculator | T089,T055 | SPEC-007 |
| T091 | E09 | P0 | Implement causal-cluster exposure mapper | T060,T090,T072 | SPEC-007 |
| T092 | E09 | P0 | Implement versioned risk-policy service | T031,T020 | SPEC-007 |
| T093 | E09 | P0 | Implement deterministic risk assessment | T092,T090,T091,T074 | SPEC-007 |
| T094 | E09 | P0 | Implement risk decision and approval expiry | T093 | SPEC-007 |
| T095 | E09 | P0 | Implement paper order-intent service | T094,T072,T088 | SPEC-009 |
| T096 | E09 | P0 | Implement paper execution adapter V0.1 | T095,T055 | SPEC-009 |
| T097 | E09 | P0 | Implement conservative fill model | T096 | SPEC-009 |
| T098 | E09 | P0 | Implement atomic paper accounting ledger | T031,T097 | SPEC-009 |
| T099 | E09 | P0 | Implement portfolio reconciliation service | T098 | SPEC-009,SPEC-015 |
| T100 | E09 | P0 | Implement kill-switch enforcement | T020,T092,T099 | SPEC-007,SPEC-009 |
| T101 | E10 | P0 | Implement dataset-manifest registry | T032,T027,T028 | SPEC-008 |
| T102 | E10 | P0 | Implement point-in-time dataset builder skeleton | T101,T055,T056 | SPEC-008 |
| T103 | E10 | P1 | Implement feature-definition registry | T032 | SPEC-008 |
| T104 | E10 | P1 | Implement label-definition registry | T032 | SPEC-008 |
| T105 | E10 | P0 | Implement baseline strategy library | T101 | SPEC-008 |
| T106 | E10 | P0 | Implement event-study engine V0.1 | T102,T105 | SPEC-008 |
| T107 | E10 | P0 | Implement backtest engine V0.1 | T102,T105,T055 | SPEC-008 |
| T108 | E10 | P1 | Implement walk-forward and holdout runner | T107 | SPEC-008 |
| T109 | E10 | P1 | Implement parameter sensitivity runner | T107 | SPEC-008 |
| T110 | E10 | P1 | Implement regime-segmented performance report | T107,T062 | SPEC-008,SPEC-021 |
| T111 | E10 | P0 | Implement postmortem and outcome attribution service | T032,T098,T072 | SPEC-010,SPEC-030 |
| T112 | E10 | P1 | Implement calibration and belief-update registry | T111,T030 | SPEC-030 |
| T113 | E11 | P1 | Implement market regime engine V0.1 | T062,T102 | SPEC-021 |
| T114 | E11 | P1 | Implement sector state builder | T028,T055,T113 | SPEC-022 |
| T115 | E11 | P1 | Implement supply-chain relationship importer | T060 | SPEC-023 |
| T116 | E11 | P1 | Implement weather observation adapter and normalizer | T044,T048 | SPEC-024 |
| T117 | E11 | P1 | Implement crop and agricultural state builder | T116,T028 | SPEC-024,SPEC-026 |
| T118 | E11 | P1 | Implement livestock disease state builder | T054,T028 | SPEC-026 |
| T119 | E11 | P1 | Implement commodity state and futures-curve builder | T055,T117,T118 | SPEC-026 |
| T120 | E11 | P1 | Implement geopolitical event state builder | T054,T028 | SPEC-025 |
| T121 | E11 | P1 | Implement corporate relationship mapping pipeline | T028,T064 | SPEC-027 |
| T122 | E11 | P1 | Implement institutional flow normalization | T044,T048,T055 | SPEC-028 |
| T123 | E11 | P1 | Implement domain event materiality ranking | T114,T117,T119,T120 | SPEC-022,SPEC-024,SPEC-025,SPEC-026 |
| T124 | E11 | P1 | Implement domain intelligence read models | T113,T114,T117,T119,T120,T121 | SPEC-002 |
| T125 | E12 | P0 | Create FastAPI application and health endpoints | T005,T011,T021 | SPEC-012,SPEC-015 |
| T126 | E12 | P0 | Implement API authentication and authorization middleware | T017,T125 | SPEC-012,SPEC-013 |
| T127 | E12 | P0 | Implement canonical API error responses | T014,T125 | SPEC-012 |
| T128 | E12 | P0 | Implement source event evidence and world-state query endpoints | T043,T061,T064,T062,T125 | SPEC-012 |
| T129 | E12 | P0 | Implement hypothesis thesis and committee endpoints | T071,T072,T087,T125 | SPEC-012 |
| T130 | E12 | P0 | Implement portfolio risk order and journal endpoints | T090,T094,T095,T099,T111,T125 | SPEC-012 |
| T131 | E12 | P0 | Generate typed frontend API client | T125,T126,T127,T128,T129,T130 | SPEC-011,SPEC-012 |
| T132 | E12 | P0 | Build Today command-center page | T006,T131,T128,T130 | SPEC-011 |
| T133 | E12 | P0/P1 | Build decision detail and explainability page | T076,T131,T129 | SPEC-011,SPEC-020 |
| T134 | E12 | P1 | Build portfolio risk research and system-health pages | T131,T130,T111 | SPEC-011 |
| T135 | E13 | P0 | Implement structured logging configuration | T013,T125 | SPEC-013,SPEC-015 |
| T136 | E13 | P0 | Implement application health aggregation | T050,T135,T093,T099 | SPEC-015,SPEC-018 |
| T137 | E13 | P0/P1 | Implement core metrics instrumentation | T135 | SPEC-015 |
| T138 | E13 | P0 | Implement alert rule engine skeleton | T136,T137 | SPEC-015 |
| T139 | E13 | P0 | Implement backup command and manifest | T032,T045 | SPEC-015 |
| T140 | E13 | P0 | Implement isolated restore command | T139 | SPEC-015 |
| T141 | E13 | P0 | Implement paper accounting reconciliation schedule | T099,T040 | SPEC-009,SPEC-015 |
| T142 | E13 | P0 | Implement source-health scheduled checks | T050,T040 | SPEC-018,SPEC-016 |
| T143 | E13 | P0 | Implement daily workflow scheduler | T039,T056,T087,T093,T099,T132 | SPEC-016 |
| T144 | E13 | P1 | Implement daily engineering/operations summary artifact | T143,T135 | SPEC-010,SPEC-015 |
| T145 | E14 | P0 | Configure backend formatting linting and type checks | T005 | SPEC-015 |
| T146 | E14 | P0 | Configure frontend lint type and build checks | T006 | SPEC-011,SPEC-015 |
| T147 | E14 | P0 | Create PostgreSQL-backed integration test environment | T021,T022 | SPEC-015 |
| T148 | E14 | P0 | Implement architecture boundary tests | T009,T147 | SPEC-000,SPEC-015 |
| T149 | E14 | P0 | Implement constitutional invariant test suite | T147,T031,T094 | SPEC-000 |
| T150 | E14 | P0 | Implement golden end-to-end trace test | T010,T056,T076,T087,T094,T095,T098,T111,T132 | SPEC-000,SPEC-015 |
| T151 | E14 | P0 | Implement failure-path golden scenarios | T150 | SPEC-000,SPEC-015 |
| T152 | E14 | P0 | Configure CI pipeline | T145,T146,T147,T148,T149,T150,T151 | SPEC-015 |
| T153 | E14 | P0 | Implement release manifest generator | T152,T008,T030 | SPEC-015 |
| T154 | E14 | P0 | Create V0.1 release checklist and sign-off | T153 | SPEC-015 |
| T155 | E15 | P1 | Create public strategy research intake workflow | T071,T101 | SPEC-017,SPEC-028 |
| T156 | E15 | P1 | Implement observable-trade behavior feature extractor | T155,T122,T055 | SPEC-008,SPEC-028 |
| T157 | E15 | P1 | Implement candidate strategy-family classifier | T156,T082 | SPEC-008 |
| T158 | E15 | P1 | Create reconstructed-strategy rule builder | T157,T071 | SPEC-008,SPEC-017 |
| T159 | E15 | P1 | Run first public strategy historical test | T158,T107 | SPEC-008 |
| T160 | E15 | P1 | Implement strategy similarity comparison report | T159 | SPEC-008 |
| T161 | E15 | P1 | Create forward paper monitor for reconstructed strategy | T159,T095 | SPEC-008,SPEC-009 |
| T162 | E15 | P1 | Create strategy reverse-engineering review template and scorecard | T155,T160,T161 | SPEC-008,SPEC-030 |
| T163 | E15 | P1 | Create public-adviser and fund disclosure research queue | T155 | SPEC-008,SPEC-028 |
| T164 | E15 | P1 | Implement reconstructed-strategy promotion gate | T159,T160,T161,T162 | SPEC-008,SPEC-030 |
| T165 | E16 | P2 | Create future institutional gap assessment | T154 | SPEC-013,SPEC-015 |
| T166 | E16 | P2 | Create future live-pilot promotion checklist placeholder | T165 | SPEC-000,SPEC-007,SPEC-009,SPEC-015 |
| T167 | E16 | P2 | Create deferred vendor decision scorecard | T165 | SPEC-012,SPEC-015 |
| T168 | E16 | P2 | Create multi-user and tenant-boundary design placeholder | T165 | SPEC-012,SPEC-013 |
