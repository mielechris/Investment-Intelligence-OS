# Superbatch 19L–19P — Permanent Runtime Parity

## Root cause

`--enable-expansion-wing` was parsed, stored, and enforced by the same-origin
snapshot route, but the server did not expose that setting in `/health` or
`/living/overview`. The frontend navigation therefore had no authenticated
runtime-capability contract. Build identity and fixture identity are not runtime
authorization.

The server now projects a fixed scalar-only `iios-runtime-capabilities-v1`
record. It is attached to the living overview after evidence-cache retrieval,
so a cached pre-activation overview cannot suppress a newly enabled server
configuration. The frontend's single Expansion Wing polling owner validates
that record before requesting `/expansion-wing/snapshot`. The browser has no
publisher, provider, broker, ledger, or execution control route.

## Truthful terminal states

| Surface | Available source | Missing/failed source | Retained evidence after refresh failure |
| --- | --- | --- | --- |
| Living factory floor | rendered payload | `LIVING_FACTORY_SOURCE_UNAVAILABLE` | existing view remains visible |
| Operating view | rendered payload | `OPTIONAL_OPERATING_SOURCE_UNAVAILABLE` | `STALE` warning |
| Capital readiness | rendered payload | `OPTIONAL_READINESS_SOURCE_UNAVAILABLE` | `STALE` warning |
| Expansion Wing | sanitized snapshot states | `UNAVAILABLE` | `STALE` |

`ASSEMBLING…` and `OPENING…` are bounded initial-request states only. A
completed failure is not described as a model warming up. The Expansion Wing
snapshot remains authoritative for 9H, sanitized 9I, 9J, candidate lineage,
multi-product lanes, paper state, and authority locks; missing values are not
converted to zero.

## Activation boundary

This batch changes source only. It does not modify the permanent bundle,
LaunchAgent, projection, publisher, paper fund, or protected services. A future
permanent activation requires a reviewed commit, rollback-backed rebuild, and
separate authorization.
