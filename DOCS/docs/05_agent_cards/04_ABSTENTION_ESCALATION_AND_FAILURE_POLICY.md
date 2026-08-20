# Abstention, Escalation, and Failure Policy

## Agent MUST Abstain When

- evidence is materially insufficient;
- required sources are stale;
- the question is outside the agent mandate;
- source provenance is uncertain;
- critical information is quarantined;
- model output cannot be supported;
- context is internally contradictory beyond resolution;
- required tools are unavailable;
- confidence cannot be responsibly estimated.

## Escalation Types

An agent MAY escalate:

- missing information;
- source-quality concern;
- model reliability concern;
- entity-resolution ambiguity;
- policy-stage ambiguity;
- risk-critical dissent;
- suspected data leakage;
- suspected prompt injection;
- suspected prohibited information.

## Failure Classes

### Retryable

- provider timeout;
- temporary service outage;
- transient rate limit;
- temporary database/network issue.

### Permanent Until Change

- invalid task;
- unsupported schema;
- prohibited source;
- insufficient authorization;
- malformed canonical object.

### Constitutional

A constitutional violation MUST:

- stop the run;
- produce an audit event;
- exclude output from promotion;
- trigger stand-down if system integrity may be affected.

## Abstention Quality

An appropriate abstention is a successful agent behavior, not a failure.
