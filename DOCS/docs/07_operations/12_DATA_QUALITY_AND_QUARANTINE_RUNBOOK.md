# Data Quality and Quarantine Runbook

## Quarantine Triggers

- unknown provenance;
- rights uncertainty;
- malformed critical fields;
- impossible timestamps;
- entity identity conflict;
- parser corruption;
- prohibited information;
- suspicious content.

## Procedure

1. Mark object QUARANTINED.
2. Exclude from reasoning.
3. Record reason.
4. Identify dependent derived objects.
5. Pause affected promotion.
6. Review source/raw payload.
7. Correct, approve, or delete according to policy.
8. Replay affected derived data if needed.
9. Record resolution.

## Critical Data Defect

If a data defect affected a paper decision:

- flag decision lineage;
- reassess thesis;
- reassess risk;
- record incident;
- preserve original state for audit.
