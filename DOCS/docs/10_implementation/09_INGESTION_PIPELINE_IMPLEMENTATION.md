# Ingestion Pipeline Implementation

## Pipeline

```text
Source Registry
→ Connector
→ Raw Object Store
→ RawRecord
→ Parser
→ ParseResult
→ Normalizer
→ Canonical Object
→ Quality Assessment
→ Downstream Event
```

## Connector Protocol

Conceptual:

```python
class Connector(Protocol):
    def discover(self, checkpoint): ...
    def fetch(self, source_item): ...
    def health(self): ...
```

## Parser Protocol

```python
class Parser(Protocol):
    parser_id: str
    version: str

    def parse(self, raw_record): ...
```

## Normalizer Protocol

```python
class Normalizer(Protocol):
    normalizer_id: str
    version: str

    def normalize(self, parse_result): ...
```

## Raw Storage Rule

Do not parse before the raw payload is durably stored.

## Deduplication

Use source-specific natural identity plus content hash.

## Revision

When same source identity has changed content:

```text
new raw version
→ revision relationship
→ new parser output
→ new canonical version if material
→ reevaluation event
```

## Quarantine

Quarantined data stops before normal reasoning retrieval.

## Logging

Each retrieval records:

- source;
- URL/provider key;
- response status;
- bytes;
- hash;
- duration;
- attempt;
- correlation ID.
