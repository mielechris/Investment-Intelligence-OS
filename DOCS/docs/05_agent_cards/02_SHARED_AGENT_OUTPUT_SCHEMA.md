# Shared Agent Output Schema

Every specialist agent SHOULD conform to the following common structure.

```json
{
  "agent_run_id": "uuid",
  "agent_id": "uuid",
  "agent_version": "string",
  "task_object_id": "uuid",
  "source_cutoff_at": "timestamp",
  "status": "COMPLETED | ABSTAINED | FAILED_RETRYABLE | FAILED_PERMANENT",
  "view": "string",
  "disposition": "LONG | SHORT | WATCH | AVOID | NO_TRADE | NONE",
  "summary": "string",
  "key_claims": [],
  "supporting_evidence_ids": [],
  "contradictory_evidence_ids": [],
  "assumptions": [],
  "missing_information": [],
  "catalysts": [],
  "invalidation_conditions": [],
  "expected_lag": null,
  "confidence": {
    "evidence": null,
    "causal": null,
    "timing": null,
    "implementation": null,
    "overall": null
  },
  "dissent_or_uncertainty": [],
  "abstention_reason": null,
  "model_id": "uuid",
  "prompt_id": "uuid",
  "prompt_version": "string",
  "retrieval_context_hash": "string",
  "cost": null,
  "latency_ms": null
}
```

## Common Rules

- `supporting_evidence_ids` MUST reference valid Evidence objects.
- `contradictory_evidence_ids` MUST be included when material contradiction exists.
- Missing evidence MUST NOT be invented.
- Confidence values SHOULD be 0–1.
- `overall` confidence MUST NOT be used directly as position size.
- `NO_TRADE` is a valid disposition.
- `NONE` is used when the agent is not authorized to express trade direction.
- `ABSTAINED` requires `abstention_reason`.
