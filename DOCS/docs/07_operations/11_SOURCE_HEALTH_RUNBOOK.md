# Source Health Runbook

## Source Health Dimensions

- reachability;
- freshness;
- retrieval success;
- schema stability;
- parse success;
- completeness;
- latency;
- revision behavior;
- rights status.

## Degraded Source

If noncritical:

- mark degraded;
- lower downstream confidence where applicable;
- continue unaffected workflows.

If critical:

- determine whether new risk must stop;
- activate stand-down if required.

## Schema Change

1. stop affected parser promotion;
2. preserve raw payload;
3. quarantine failed normalized records;
4. update parser fixture;
5. implement parser version;
6. replay from raw;
7. compare old/new outputs;
8. resume after validation.

## Source Outage

Use bounded retry.

Do not scrape unauthorized alternatives merely to keep a workflow alive.
