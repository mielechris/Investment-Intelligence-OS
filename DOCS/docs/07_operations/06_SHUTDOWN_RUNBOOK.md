# Shutdown Runbook

## Normal Shutdown

1. Stop accepting new workflows.
2. Stop scheduler from creating new jobs.
3. Allow critical in-flight jobs to finish or release leases.
4. Flush outbox and audit events.
5. Reconcile paper accounting.
6. Stop workers.
7. Stop API.
8. Stop frontend.
9. Stop cache if used.
10. Stop object storage if local.
11. Stop database last.
12. Record shutdown event.

## Emergency Shutdown

If integrity is at risk:

1. Activate stand-down.
2. Block new paper orders.
3. Preserve current state.
4. Stop risky workflows.
5. Keep audit and diagnostics available if safe.
6. Record incident.
7. Shutdown affected services.

## Lease Safety

Workers that terminate unexpectedly MUST leave jobs recoverable after lease expiration.
