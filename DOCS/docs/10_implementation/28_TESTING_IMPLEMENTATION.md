# Testing Implementation

## Test Layers

```text
unit
property
contract
integration
end-to-end
security
reliability
performance
```

## Unit

Test:

- domain invariants;
- status transitions;
- parsers;
- timestamp rules;
- risk rules;
- accounting.

## Property Tests

Examples:

```text
duplicate fill never changes state twice
cash + positions always reconcile after valid fills
risk limits never exceeded after approval
```

## Contract Tests

Use fake implementations for:

- connectors;
- market data;
- model gateway;
- object storage;
- paper broker.

## Integration

Use real PostgreSQL and object storage.

## Golden Trace

End-to-end reference scenario.

## Failure Scenarios

Must include:

- stale source;
- prompt injection;
- risk veto;
- duplicate event;
- worker crash;
- accounting mismatch;
- model outage;
- object-store outage.

## Test Naming

Use clear behavior names.

Example:

```text
test_risk_veto_prevents_paper_order_intent
```
