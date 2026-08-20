# Disaster Recovery Plan

## Disaster Classes

- machine loss;
- database loss;
- object-store loss;
- credential compromise;
- corrupted release;
- ransomware/malware;
- extended source outage;
- model-provider outage;
- severe data corruption.

## Recovery Priorities

1. preserve safety;
2. preserve audit;
3. restore authoritative database;
4. restore raw-source artifacts;
5. restore risk and portfolio state;
6. restore workflow;
7. restore command center;
8. restore research workloads last.

## Minimum Recovery Assets

- database backup;
- object-store backup;
- Git repository;
- release manifest;
- migration history;
- configuration versions;
- secure credential recovery process.

## Disaster Mode

System remains stand-down until:

- state integrity verified;
- accounting reconciled;
- critical dependencies healthy;
- operator approves resumption.

## Disaster Recovery Test

Perform periodic restore into isolated test environment.

Document:

- restore time;
- missing artifacts;
- failures;
- corrective actions.
