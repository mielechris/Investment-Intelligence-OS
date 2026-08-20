# Field Dictionary Template

# Object Name

**Canonical name:**  
**Owning module:**  
**PostgreSQL schema:**  
**Schema version:**  
**Source specification:**  
**Architecture reference:**  

## Purpose

Describe the object.

## Fields

| Field | Type | Required | Default | Unit | Meaning | Validation | Point-in-Time Rule |
|---|---|---:|---|---|---|---|---|
| field | type | yes/no | value | unit | meaning | rule | rule |

## Foreign Keys

| Field | References | Retention / Delete Behavior |
|---|---|---|
| field | object | behavior |

## Unique Constraints

- Constraint

## Check Constraints

- Constraint

## Indexes

- Index and query reason

## Status Lifecycle

```text
STATE_A → STATE_B → STATE_C
```

## Versioning

Describe what creates a new version.

## Provenance

Describe source lineage.

## Security / Rights

Describe classification and access.

## Retention

Describe retention and deletion.

## Example

```json
{}
```

## Required Tests

- valid object;
- invalid type;
- missing required field;
- migration;
- historical query;
- rights boundary.
