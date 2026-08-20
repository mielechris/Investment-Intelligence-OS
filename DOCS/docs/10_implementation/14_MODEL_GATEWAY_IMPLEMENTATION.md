# Model Gateway Implementation

## One Gateway

All model calls go through:

```text
ModelGateway
```

No agent directly imports provider SDKs.

## Internal Request

Conceptual:

```python
ModelRequest(
    model_policy_id=...,
    prompt_id=...,
    messages=...,
    tools=...,
    output_schema=...,
    timeout=...,
    correlation_id=...
)
```

## Gateway Responsibilities

- choose approved provider/model;
- enforce data restrictions;
- redact secrets;
- enforce timeout;
- enforce cost budget;
- enforce structured output;
- normalize errors;
- record provider request ID;
- record model ID;
- record usage;
- record latency.

## Model Registry

No aliases like `latest` in historical lineage.

Persist exact provider identifier.

## Fallback

Only approved fallback models.

Fallback must be recorded.

## Tests

- approved model;
- unapproved model;
- timeout;
- structured-output failure;
- fallback;
- cost limit;
- secret redaction.
