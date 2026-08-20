# Investment Intelligence OS
## Constitution-to-Architecture Traceability Matrix — v0.1

---

## Purpose

Map the governing controls in `../01_project_charter/02_SYSTEM_CONSTITUTION.md` to technical components and required tests.

---

| Constitutional Control | Architecture Implementation | Primary Documents | Required Verification |
|---|---|---|---|
| Evidence before opinion | Evidence objects, claim validation, support and contradiction | 11, 12 | Unsupported claim rejected |
| Lawful public or licensed information | Source registry, rights metadata, quarantine | 03, 09, 18 | Prohibited source excluded |
| Timestamp integrity | Four timestamps, point-in-time datasets, revisions | 06, 07, 15 | Future revision leakage test |
| No source is an oracle | Multi-domain world model, skeptic, counter-chain | 11, 12, 13 | Single-source high-confidence promotion blocked |
| Separate reasoning layers | Distinct claim, hypothesis, thesis, decision objects | 07, 12 | Inference not presented as fact |
| Provenance mandatory | Source-to-outcome lineage and explainability packet | 06, 11, 12 | Golden trace reconstructs lineage |
| Counter-case required | Counter-chain and skeptic agent | 12, 13 | Thesis without counter-case blocked |
| Preserve dissent | Dissent records and committee contract | 13 | Disagreement remains visible |
| Risk veto authority | Independent deterministic risk module | 04, 14 | Veto blocks order |
| Confidence is not leverage | Decomposed confidence and separate sizing | 12, 14 | High confidence cannot exceed limits |
| Backtests try to disprove | Baselines, holdout, walk-forward, sensitivity | 15, 22 | In-sample-only promotion blocked |
| Strategy reconstruction is hypothesis | Strategy research workflow and unknowns | 15 | Exact-copy claim rejected without disclosure |
| Market reaction is not proof | Benchmarks, concurrent-event controls, counter-chain | 12, 15 | Event study requires controls |
| Model authority bounded | Model gateway, tools, output validation | 13, 18 | Agent cannot use prohibited tool |
| Abstention valid | Agent abstention, no-trade, stand-down | 12, 13, 14 | Insufficient evidence returns no-trade |
| Paper before live | Environment enforcement and paper adapter | 05, 14, 18 | V1 cannot load live adapter |
| Audit source to outcome | Audit module, IDs, logs, journal, golden trace | 04, 06, 19, 22 | Decision reconstructable |
| Learn process, not only P&L | Postmortem and outcome attribution | 15 | Lucky poor-process trade not promoted |
| Complexity earns place | Baselines and deferred specialized stores | 02, 20, 21 | Complex component requires measured benefit |
| Security and safe operation | Least privilege, health, stand-down, recovery | 18, 19 | Critical failure disables new risk |
| Human accountability | Identity, approvals, ADRs, audit | 03, 18, 23 | Material override records actor and reason |
| Capital growth not guaranteed | Paper-only research objective and risk architecture | 01, 14, 15 | No acceptance test depends on guaranteed wealth |

---

## Traceability Rule

Every future specification must cite:

- governing constitutional article or principle;
- architecture component;
- acceptance test;
- owning module.

Every implementation ticket must link to its specification and test.
