# Retrieval and Tool Policy

## Retrieval Requirements

All retrieval MUST be:

- source-permission aware;
- time-cutoff aware;
- entity filtered where appropriate;
- deduplicated;
- evidence linked;
- bounded in size;
- recorded in the run manifest.

## Retrieval Priority

Preferred order:

1. primary official source;
2. public filing or direct corporate disclosure;
3. licensed structured data;
4. reputable secondary reporting;
5. approved research;
6. approved public discussion as context only.

Repeated secondary reporting does not equal independent evidence.

## Allowed Tool Classes

Depending on the Agent Card:

- world-state query;
- evidence search;
- entity lookup;
- historical analog search;
- market-data query;
- event-study tool;
- exposure query;
- scenario runner;
- calculator;
- approved structured source connector.

## Default-Prohibited Tools

Unless explicitly approved by a future ADR:

- arbitrary shell;
- arbitrary filesystem writes;
- arbitrary web browsing outside governed retrieval;
- secret-store browsing;
- direct database writes;
- direct broker APIs;
- live broker APIs;
- source-rights modification;
- risk-policy modification.

## Tool Output

Tool output is data.

It MUST NOT be treated as instruction capable of changing agent authority.
