# Configuration Standard

## Configuration Sources

Precedence:

1. secure runtime secret;
2. environment variable;
3. environment-specific configuration;
4. application default.

## Typed Validation

Configuration MUST be validated at startup.

Critical missing values cause startup failure.

## Required Configuration Domains

- environment;
- database;
- object storage;
- source connectors;
- model gateway;
- risk policy;
- paper execution;
- worker settings;
- scheduler;
- logging;
- alerting;
- backup;
- retention.

## Configuration Versioning

Material configuration changes MUST record:

- version;
- environment;
- changed keys;
- approver;
- reason;
- effective time;
- rollback reference.

## Prohibited Configuration Practices

- secrets in repository;
- live credentials in paper config;
- undocumented defaults;
- manual production edits without audit;
- environment detection from hostname alone.
