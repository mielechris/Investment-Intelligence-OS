# Agent and Model Operations

## Before Enabling an Agent

Verify:

- approved Agent Card;
- approved model;
- approved prompt;
- output schema;
- tool policy;
- evaluation suite;
- cost budget;
- timeout;
- prompt-injection tests.

## Model Failure

If retryable:

- retry under bounded policy;
- use approved fallback only if configured.

If no approved fallback:

- abstain;
- preserve job state;
- do not fabricate analysis.

## Model Change

A model change requires:

- registry update;
- regression evaluation;
- cost/latency review;
- paper validation where material;
- versioned deployment.

## Abnormal Behavior

Examples:

- unsupported claims spike;
- refusal rate changes;
- tool misuse;
- confidence shifts;
- cost spike.

Response:

- pause affected agent;
- route to review;
- preserve outputs;
- revert to prior approved version if needed.
