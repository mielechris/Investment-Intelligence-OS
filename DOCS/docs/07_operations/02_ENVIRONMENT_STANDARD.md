# Environment Standard

## Development

Purpose:

- local coding;
- unit tests;
- fixtures;
- experimental prompts.

Restrictions:

- no production credentials;
- no live broker credentials;
- no authoritative paper history required.

## Test

Purpose:

- integration tests;
- replay;
- migration tests;
- failure simulation;
- golden trace.

Restrictions:

- synthetic/replayed state only.

## Paper

Purpose:

- real-time research;
- real-time source ingestion;
- paper decisions;
- simulated orders and positions.

Requirements:

- explicit PAPER environment flag;
- paper-only execution adapter;
- current risk policy;
- auditable source cutoff;
- backups enabled.

## Live

Status:

- disabled in V1;
- no deployment;
- no credentials;
- no route.

## Isolation

Each environment uses separate:

- database;
- object-store namespace;
- credentials;
- logs;
- broker adapters;
- source credentials where appropriate;
- model policy where appropriate.

## Environment Assertion

Every startup MUST verify environment identity before accepting work.
