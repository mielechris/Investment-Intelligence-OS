# Research Experiment Registry

Every experiment receives a durable record.

## Required Fields

- experiment ID;
- title;
- hypothesis ID/version;
- strategy ID/version;
- research question;
- owner;
- date created;
- dataset manifest;
- feature versions;
- parameters;
- benchmark;
- primary metric;
- secondary metrics;
- train period;
- validation period;
- holdout period;
- number of variants tested;
- code commit;
- dependency lock;
- random seed;
- result artifact;
- conclusion;
- next action.

## Experiment Status

```text
PLANNED
RUNNING
COMPLETED
INVALID
REJECTED
PROMOTED
SUPERSEDED
```

## Invalid Experiment

Reasons may include:

- leakage;
- corrupted data;
- incorrect benchmark;
- execution model error;
- missing source rights;
- unreproducible output.

Invalid experiments remain in history.
