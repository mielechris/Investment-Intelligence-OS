# Superbatch 19R–19T — Living Overview Latency

## Classification and measured cause

The rollback runtime reproduced the failure without mutation. A cache-miss
`GET /living/overview` completed in 3.026 seconds, while the immediately
following cache hit completed in 0.013 seconds. Direct bounded probes measured
`GET /system/status` at 0.005 seconds and the dislocation source at 0.100
seconds. The factory-intelligence source exceeded a four-second observation
bound without returning bytes.

The pre-repair cache expired every five seconds, exactly matching the active
Living Factory browser polling interval. The first request after expiration
owned a synchronous refresh and waited for the slow source's three-second
timeout. Other handler threads could receive retained evidence only after a
validated snapshot already existed. A cold request had no sub-three-second
fallback. This is `SYNCHRONOUS_CACHE_MISS_OPTIONAL_SOURCE_TIMEOUT`, not an HTTP
listener, JSON serialization, or projection-integrity failure.

## Read path and bounded instrumentation

The path is:

1. threaded preview HTTP handler;
2. process-local cache lookup;
3. validation-stack file stat/read/JSON parsing;
4. two parallel read-only Backend GETs;
5. telemetry assembly and fixed safety projection;
6. JSON serialization and response.

The overview handler does not open SQLite or the operational ledger. Those
operations, character derivation, and story derivation may occur behind the
Backend factory-intelligence endpoint and cannot be attributed safely by this
read-only sidecar. Their timing fields therefore remain `null` with the fixed
category `UNAVAILABLE_AT_READ_ONLY_BOUNDARY`; the sidecar never invents a
duration. Instrumentation contains durations and fixed categories only—never
paths, source values, SQL results, exceptions, or credentials.

The audit found no retry loop and no sequential optional-source timeout in the
sidecar. Backend GETs were already parallel. Source JSON reads open one regular
file generation, so an atomic same-directory publisher replacement cannot
produce a mixed read. The request path performs no full ledger scan and no
asset-directory hash scan. The HTTP server is threaded. The 269 KB cached
response serialized and transferred inside the measured 13 ms cache-hit
request. Client disconnects are now contained without retrying or invalidating
the cache.

## Repair contract

- The cache TTL is aligned to the unified 15-second snapshot poll.
- One bounded worker owns refresh; concurrent readers never run the loader.
- An expired validated snapshot is returned immediately while refresh runs.
- Evidence age, freshness, served time, refresh generation, fixed failure
  category, lock wait, and refresh duration are projected as scalar metadata.
- The original evidence `generated_at` is not changed when retained.
- Evidence older than the stale threshold is explicitly `STALE` and
  `evidence_current=false`.
- A cold slow source returns `FACTORY_SOURCE_UNAVAILABLE` inside a 500 ms wait
  bound while the one worker finishes or times out.
- Invalid cache entries and invalid refresh results are never served.
- A failed refresh preserves the prior validated snapshot and records only a
  fixed sanitized failure category.
- HEAD coalesces through the same cache and emits no response body. Mutations
  remain HTTP 405.
- Fixture-isolated acceptance never contacts Backend 8002 or a ledger.
- Shutdown joins the single refresh worker; there is no scheduler, daemon, or
  additional persistent service.

## Operational boundary

This batch changes source and deterministic tests only. It does not alter the
permanent 5176, 5177, 5185, 8002, or publisher processes; projection evidence;
paper state; LaunchAgents; providers; Keychain; brokers; ledgers; Production;
or `main`.
