# Shared Agent Runtime Contract

## 1. Role

Every IIOS agent is a bounded analyst operating inside the governed Agent Runtime.

Agents do not own authoritative financial or operational state.

## 2. Required Runtime Inputs

Every run MUST receive:

- `agent_definition_id`
- `agent_version`
- `task_type`
- `task_object_id`
- `source_cutoff_at`
- `environment`
- approved retrieval context
- approved tool list
- model policy
- prompt version
- maximum steps
- maximum cost
- timeout
- correlation ID

## 3. Required Runtime Outputs

Every run MUST produce either:

- valid structured analysis;
- abstention;
- retryable failure;
- permanent failure.

A conversational paragraph alone is not a valid production output.

## 4. Authority Boundary

Agents MAY:

- retrieve governed evidence;
- summarize;
- compare;
- classify;
- reason;
- calculate through approved tools;
- challenge assumptions;
- propose hypotheses;
- recommend committee actions.

Agents MUST NOT:

- place or modify orders;
- alter portfolio accounting;
- alter risk policy;
- alter source rights;
- modify governance documents;
- create live broker authority;
- access arbitrary filesystem/network/shell;
- silently change models or prompts.

## 5. Evidence Rule

Any material factual statement MUST be supported by evidence IDs or explicitly labeled unsupported and excluded from promotion.

## 6. Time Rule

Retrieval MUST enforce:

```text
evidence.market_available_at <= source_cutoff_at
```

unless the task is explicitly a current-state or postmortem task.

## 7. Bounded Execution

Every run MUST enforce:

- max steps;
- timeout;
- token limit where applicable;
- cost budget;
- tool-call budget;
- debate budget when applicable.

## 8. Immutability

Completed `AgentOutput` objects are immutable.

Corrections create a new run linked to the prior run.

## 9. Audit

Every run records:

- exact model;
- exact prompt;
- retrieval policy;
- tool calls;
- cited evidence;
- latency;
- cost;
- output status;
- errors;
- correlation ID.
