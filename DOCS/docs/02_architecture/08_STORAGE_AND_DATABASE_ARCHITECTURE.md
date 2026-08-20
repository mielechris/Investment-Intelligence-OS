# Investment Intelligence OS
## Storage and Database Architecture — v0.1

---

## 1. Storage Strategy

IIOS uses three storage classes:

1. PostgreSQL for governed transactional and queryable state
2. Object storage for immutable and large artifacts
3. Optional cache for disposable acceleration

No fourth hidden source of truth is permitted.

---

## 2. PostgreSQL Role

PostgreSQL stores:

- source registry;
- connector state;
- raw-record metadata;
- canonical events;
- market data required for operational decisions;
- entities and relationships;
- evidence and claims;
- causal reasoning;
- hypotheses and theses;
- agent and committee records;
- risk and portfolio state;
- paper orders and fills;
- research manifests and results;
- model and prompt registry;
- jobs, outbox, inbox, audit, and incidents.

PostgreSQL is selected because V1 requires strong transactions, relational integrity, flexible structured metadata, text search, and colocated vector retrieval without introducing several operational databases.

---

## 3. Logical Database Schemas

Recommended logical schemas:

| Schema | Ownership |
|---|---|
| `platform` | Configuration, users, releases, feature flags |
| `source` | Source registry, rights, endpoints, health |
| `ingest` | Retrievals, raw metadata, parse and normalization results |
| `market` | Instruments, calendars, bars, quotes, curves, corporate actions |
| `knowledge` | Entities, aliases, relationships, world state, regimes |
| `evidence` | Evidence, claims, support, contradiction |
| `reasoning` | Chains, hypotheses, theses, explainability |
| `agents` | Agents, prompts, models, runs, outputs |
| `decision` | Committee sessions, decisions, dissent |
| `portfolio` | Accounts, cash, positions, exposures, snapshots |
| `risk` | Policies, assessments, decisions, kill-switch state |
| `execution` | Order intents, paper orders, fills, costs |
| `research` | Datasets, strategies, tests, benchmarks, results |
| `learning` | Postmortems, attribution, calibration, belief updates |
| `workflow` | Job definitions, runs, leases, outbox, inbox |
| `audit` | Append-only audit events and incidents |

Physical separation into different databases is deferred.

---

## 4. Object Storage

Object storage contains:

- original HTML, JSON, XML, CSV, PDF, audio, image, or text payload;
- raw market-data batch files where licensed;
- extracted document text;
- model request and response bundles where retention is approved;
- large backtest results;
- reports and chart images;
- export bundles;
- database backup artifacts.

Object keys should be deterministic and content-aware.

Example:

```text
raw/{source_id}/{yyyy}/{mm}/{dd}/{raw_record_id}/{content_hash}.{ext}
research/{strategy_id}/{run_id}/manifest.json
reports/{yyyy}/{mm}/{dd}/{report_id}.md
```

---

## 5. Raw Immutability

Raw objects use:

- content hash;
- size;
- media type;
- retrieval metadata;
- object-store version or immutable key;
- encryption metadata;
- retention class.

The database points to the object.

A later parser never overwrites the raw object.

---

## 6. Embeddings and Vector Search

Embeddings are stored with governed source and version metadata.

Initial implementation uses PostgreSQL with the vector extension so semantic search remains close to:

- source permissions;
- entity filters;
- time cutoffs;
- trust scores;
- document versions.

Embedding records include:

- source object ID;
- chunk ID;
- embedding model;
- embedding dimensions;
- created time;
- text hash;
- access classification;
- validity period.

A separate vector database is deferred until measured scale or isolation needs justify it.

---

## 7. Full-Text Search

PostgreSQL full-text indexes may support:

- source-document search;
- evidence search;
- thesis and journal search;
- entity-aware document retrieval.

Full-text and vector retrieval should be combined with deterministic filters such as:

- source class;
- publication cutoff;
- entity;
- geography;
- policy stage;
- asset class;
- rights classification;
- trust threshold.

---

## 8. Relational Versus JSON Data

Use relational columns for:

- IDs;
- statuses;
- timestamps;
- foreign keys;
- numeric values;
- fields used for joins, constraints, and frequent filters.

Use JSON-compatible columns for:

- source-specific metadata;
- provider payload fragments;
- extensible score explanations;
- rarely queried optional details.

Do not hide core domain relationships inside opaque JSON.

---

## 9. Constraints

The database must enforce, where practical:

- unique source natural keys;
- non-null lineage IDs;
- valid status values;
- positive quantities where required;
- order and fill relationships;
- one active paper-mode configuration;
- unique outbox event IDs;
- unique inbox consumer/event pairs;
- no duplicate raw content per source and retrieval identity;
- portfolio accounting references;
- valid environment mode.

Application validation supplements but does not replace database constraints.

---

## 10. Transaction Boundaries

Examples of atomic transactions:

- raw metadata plus object reference plus outbox event;
- canonical event plus revision link plus outbox event;
- committee decision plus audit event;
- risk decision plus audit event;
- paper order state change plus ledger entry plus outbox event;
- paper fill plus position and cash updates plus portfolio snapshot;
- model registry update plus deployment audit event.

External API calls do not remain inside long database transactions.

---

## 11. Transactional Outbox

State changes that require downstream handling write an outbox event in the same transaction.

Dispatcher behavior:

- claim unpublished event;
- publish to internal handler or future broker;
- record delivery attempt;
- retry with backoff;
- mark published;
- preserve payload and schema version.

Consumers use an inbox table for idempotency.

---

## 12. Indexing Strategy

Initial indexes prioritize:

- source and external key;
- observed and market-available time;
- event type and entity;
- instrument and timestamp;
- active thesis status;
- portfolio and position;
- job status and next-attempt time;
- outbox unpublished state;
- audit correlation ID;
- full-text vectors;
- embedding similarity with approved filters.

Index creation must be driven by query plans and measured workload.

---

## 13. Partitioning Strategy

Do not partition every table in V1.

Candidate future partitions:

- market bars;
- quotes;
- audit events;
- raw retrieval metadata;
- high-volume model runs;
- job history.

Partition by time only when table size and maintenance evidence justify it.

---

## 14. Retention

Retention is object-class specific.

Examples:

- raw primary-source records: long-term or permanent unless rights require otherwise;
- audit events: long-term;
- paper decisions and accounting: long-term;
- transient cache: short;
- detailed model payloads: configurable based on rights, security, cost, and reproducibility;
- redundant derived features: reproducible and eligible for pruning;
- quarantined prohibited data: remove under incident procedure.

Retention changes require an ADR.

---

## 15. Database Migrations

Schema changes use version-controlled migrations.

Rules:

- migration is reviewed;
- upgrade and rollback or forward-repair plan exists;
- migrations run explicitly during deployment;
- destructive changes use staged migration;
- data backfill is separate from schema lock where practical;
- old application compatibility is considered;
- migration status is visible.

---

## 16. Backup and Recovery

Backups include:

- PostgreSQL base or logical backup;
- object-store version or snapshot;
- configuration excluding raw secrets;
- migration history;
- release manifest.

Recovery must verify:

- referential integrity;
- object links;
- paper ledger reconciliation;
- latest audit sequence;
- job leases;
- environment mode;
- risk-policy version.

---

## 17. Storage Acceptance Tests

- raw object is unchanged after parser upgrades;
- source record can be replayed from raw storage;
- database transaction and outbox commit together;
- duplicate event delivery produces one effect;
- point-in-time query excludes later revisions;
- portfolio fill update is atomic;
- backup restores a complete decision lineage;
- cache loss does not lose authoritative state;
- embedding retrieval respects source permissions and time cutoff.
