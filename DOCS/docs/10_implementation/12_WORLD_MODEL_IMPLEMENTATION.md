# World Model Implementation

## Core Services

Implement:

```text
EntityService
EntityResolutionService
RelationshipService
PolicyStateProjector
RegimeService
WorldStateSnapshotService
```

## Entity Resolution Order

1. exact external ID;
2. approved alias;
3. normalized name + type/geography;
4. probabilistic suggestion;
5. manual review for ambiguous high-impact match.

## Policy State

Do not let one event overwrite full policy lifecycle.

Represent transitions.

Example:

```text
ANNOUNCED_INTENT
→ FORMALLY_ISSUED
→ LEGALLY_EFFECTIVE
→ IMPLEMENTATION_STARTED
```

## Snapshot

Snapshot creation:

1. choose `source_cutoff_at`;
2. query all eligible state;
3. include source-health status;
4. include stale domains;
5. include regime state;
6. hash included source/version set;
7. persist immutable snapshot.

## Read API

Need:

```text
get_current_world_state()
get_world_state(as_known_at)
get_entity_exposure(entity_id)
get_policy_state(policy_id, as_known_at)
```

## Tests

- later evidence excluded;
- entity merge preserves prior decision;
- White House meeting does not create contract;
- policy reversal creates new state.
