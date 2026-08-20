# Configuration and Secrets Implementation

## Settings Model

Create a typed settings class.

Conceptual fields:

```python
environment
database_url
object_store_endpoint
object_store_bucket
model_provider_settings
paper_execution_settings
logging_settings
scheduler_settings
risk_policy_reference
```

## Environment Enum

```python
DEVELOPMENT
TEST
PAPER
LIVE
```

V1 startup guard:

```python
if environment == LIVE:
    raise LiveExecutionDisabledError(...)
```

## Secret Type

Use a secret-string type or equivalent to prevent accidental representation.

Never print settings blindly.

## Configuration Validation

Fail startup when:

- database URL missing;
- object storage missing;
- PAPER environment not explicit for paper process;
- risk-policy reference absent in paper environment.

## Secret Access Boundary

Create:

```text
SecretProvider
└── EnvironmentSecretProvider  # V0.1
```

Future providers may implement the same interface.

## Tests

- valid PAPER config;
- missing database URL;
- invalid environment;
- secret redaction;
- LIVE mode rejection.
