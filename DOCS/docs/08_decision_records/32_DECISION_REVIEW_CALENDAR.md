# Decision Review Calendar

Decision reviews are trigger-based first and calendar-based second.

## Monthly Review

Review:

- deferred vendor decisions;
- model/provider architecture;
- source reliability;
- operational complexity;
- risk assumptions;
- paper execution realism.

## Quarterly Review

Review all accepted architecture ADRs for:

- original assumption validity;
- scale changes;
- security changes;
- cost changes;
- provider changes;
- institutional requirements.

## Immediate Review Triggers

Review the relevant ADR when:

- a critical incident exposes architectural weakness;
- a strategy or data source requires prohibited authority;
- live-pilot planning begins;
- multi-user support begins;
- major vendor lock-in becomes necessary;
- PostgreSQL becomes a measured bottleneck;
- job volume requires external workflow/event infrastructure;
- a dedicated graph/vector store appears justified;
- a model provider materially changes terms or behavior.

## Review Outcome

Each review produces one of:

```text
KEEP
AMEND_WITH_NONMATERIAL_NOTE
SUPERSEDE
DEPRECATE
RETIRE
DEFER_FURTHER
```
