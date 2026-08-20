# Retention, Lineage, and Deletion

## Default Long-Term Records

Retain long-term unless rights or law require otherwise:

- primary-source raw records;
- decision lineage;
- paper accounting;
- journal/postmortems;
- research manifests/results;
- strategy versions;
- model/prompt versions used in decisions;
- audit;
- incidents;
- architecture/governance versions.

## Reproducible Derived Data

May be pruned if:

- reproducible from retained data;
- not required for audit;
- rights allow pruning;
- deletion is documented.

Examples:

- temporary embeddings;
- caches;
- intermediate features;
- duplicate chart artifacts.

## Corrections

Material corrections create:

- new version;
- supersession relationship;
- reason;
- actor/process;
- timestamp.

Do not erase prior decision context.

## Deletion by Policy

When deletion is required:

1. identify scope;
2. identify dependent artifacts;
3. determine derivative-deletion requirement;
4. record deletion event;
5. preserve safe audit metadata where permitted;
6. verify backup handling.

## Export Bundle

A governed export SHOULD include:

- manifest;
- canonical IDs;
- schema versions;
- source rights notes;
- hashes;
- cutoff;
- code/model/prompt versions;
- included artifacts.
