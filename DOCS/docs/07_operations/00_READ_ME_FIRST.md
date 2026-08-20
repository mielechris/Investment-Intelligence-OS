# Investment Intelligence OS
## Package 07 — Operations — v0.1

**Destination:** `docs/07_operations/`  
**Governing packages:** 01 Project Charter, 02 Architecture, 03 Specifications, 04 Data Catalog, 05 Agent Cards, 06 Research  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading only

---

## Purpose

This package defines how IIOS is operated safely and repeatedly.

It covers:

- local startup and shutdown;
- environments;
- configuration;
- secrets;
- scheduled workflows;
- source health;
- data freshness;
- paper portfolio operations;
- risk-state operations;
- stand-down and kill switches;
- model/provider failures;
- incidents;
- logging and monitoring;
- backups;
- restore;
- migrations;
- releases;
- rollbacks;
- daily, weekly, and monthly reviews;
- cost controls;
- access controls;
- disaster recovery;
- operator checklists.

---

## Operations Documents

| File | Purpose |
|---|---|
| `01_OPERATING_MODEL.md` | Overall operating model |
| `02_ENVIRONMENT_STANDARD.md` | Development, test, paper, future live |
| `03_CONFIGURATION_STANDARD.md` | Runtime configuration rules |
| `04_SECRETS_AND_CREDENTIALS_RUNBOOK.md` | Secrets handling |
| `05_STARTUP_RUNBOOK.md` | Safe system startup |
| `06_SHUTDOWN_RUNBOOK.md` | Safe system shutdown |
| `07_DAILY_OPERATING_RUNBOOK.md` | Daily workflow |
| `08_PREMARKET_AND_MORNING_CHECKLIST.md` | Pre-market checks |
| `09_INTRADAY_MONITORING_RUNBOOK.md` | Intraday operations |
| `10_POST_CLOSE_RUNBOOK.md` | After-close workflow |
| `11_SOURCE_HEALTH_RUNBOOK.md` | Source failures and freshness |
| `12_DATA_QUALITY_AND_QUARANTINE_RUNBOOK.md` | Bad data handling |
| `13_AGENT_AND_MODEL_OPERATIONS.md` | Model/agent operations |
| `14_COMMITTEE_OPERATIONS.md` | Committee workflow operations |
| `15_PORTFOLIO_AND_RISK_OPERATIONS.md` | Risk and portfolio controls |
| `16_PAPER_EXECUTION_OPERATIONS.md` | Paper order/fill operations |
| `17_STAND_DOWN_AND_KILL_SWITCH_RUNBOOK.md` | Safe-stop procedures |
| `18_INCIDENT_RESPONSE_RUNBOOK.md` | Incident management |
| `19_OBSERVABILITY_AND_ALERTING.md` | Logs, metrics, health, alerts |
| `20_BACKUP_RUNBOOK.md` | Backup process |
| `21_RESTORE_AND_RECOVERY_RUNBOOK.md` | Restore process |
| `22_DATABASE_MIGRATION_RUNBOOK.md` | Migrations |
| `23_RELEASE_RUNBOOK.md` | Release process |
| `24_ROLLBACK_RUNBOOK.md` | Rollback process |
| `25_COST_AND_USAGE_OPERATIONS.md` | Model/data/compute cost |
| `26_ACCESS_CONTROL_OPERATIONS.md` | User/service access |
| `27_WEEKLY_REVIEW_RUNBOOK.md` | Weekly review |
| `28_MONTHLY_REVIEW_RUNBOOK.md` | Monthly review |
| `29_DISASTER_RECOVERY_PLAN.md` | Severe outage plan |
| `30_OPERATIONS_ACCEPTANCE_CHECKLIST.md` | Package validation |
| `31_RUNBOOK_TEMPLATE.md` | Reusable runbook template |

---

## Operational Prime Directive

If critical state is unreliable:

```text
Do not create new risk.
Preserve state.
Surface the failure.
Record the incident.
Recover deliberately.
```

Availability is secondary to correctness.
