# Agent Runtime Implementation

## Agent Definition

Load fields defined in Package 05.

## Runtime Sequence

```text
task
→ load AgentDefinition
→ verify permitted sources/tools
→ build governed retrieval context
→ assemble prompt
→ call ModelGateway
→ validate structured output
→ validate evidence IDs
→ persist AgentRun/AgentOutput
```

## Tool Registry

Each tool has:

- ID;
- description;
- argument schema;
- authorization;
- execution timeout;
- audit policy.

## Default Deny

An agent can only call tools listed in its Agent Card.

## Context Construction

Context retrieval must enforce:

```text
rights approved
market_available_at <= source_cutoff_at
deduplicated
bounded size
```

## Prompt Injection

Wrap external content as data.

Do not allow retrieved content to define system instructions or tool permission.

## Abstention

Valid successful output:

```json
{
  "status": "ABSTAINED",
  "abstention_reason": "Critical implementation evidence is unavailable."
}
```

## Immutability

Completed outputs are not edited.

Create a new run for correction.
