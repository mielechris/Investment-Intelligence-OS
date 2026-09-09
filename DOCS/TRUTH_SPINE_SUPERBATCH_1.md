# Canonical truth spine — isolated governed replay

## Scope and status

This is an opt-in, zero-spend replay path, not a permanent deployment or proof of live investment research. Existing operational entry points remain unchanged without `IIOS_TRUTH_SPINE_CONFIG`. No operational session is reopened. No paper authorization exists in this batch. Financial Datasets is used only as the provenance of existing licensed evidence; no new provider, broker or model integration is claimed.

The actual `app:app` backend, `truth_spine_service --role scheduler`, and `truth_spine_service --role publisher` run from the same isolated immutable package. These new service entry points are real processes, not substituted legacy scheduler threads. Permanent legacy schedulers are deliberately not started in isolated mode. This proves the new replay topology, not compatibility with every permanent legacy workflow.

## Canonical topology

`truth_spine_contract.Topology` is the strict machine-readable schema. `record()` emits canonical ASCII JSON with sorted keys, compact separators and one trailing newline. SHA-256 excludes only the top-level `content_hash`. Unknown fields, invalid UTC/date/path/hash values, unexpected provider/model routes, duplicate authority fields, or any true authority fail validation.

The record binds source commit, release/manifest, dedicated runtime/interpreter/manifest, ledger snapshot identity/path/schema, market date, session/plan/generation, publisher, frontend inventory, provider/model routes, five locked authorities, creation time and rollback parent. Modes distinguish development, isolated shadow and permanent production; the runnable implementation currently accepts only isolated shadow. Phase is preserved independently: `SESSION_CLOSED` never becomes `INSTALLED_DISABLED`.

Mutable ledger, projection and heartbeat files live outside the immutable package. Service configuration hash-binds the active topology and the three exact input files. Runtime verification covers the copied interpreter/dependencies and declared OS Framework dependencies. macOS process discovery verifies the actual manifest-bound Framework executable; each worker independently checks its dedicated launcher identity. No process lookup is replaced by a test callback.

## Health contracts

| Endpoint | Isolated result | Evidence |
|---|---|---|
| `/health/live` | 200 LIVE | Responding backend PID; no factory-readiness claim |
| `/health/ready` | 200 only for coherent internal replay | Package/runtime hashes, isolated ledger, real scheduler/publisher PIDs and fresh heartbeats, matching persisted projection |
| `/health/market-readiness` | 503 NOT_READY | Closed historical session, governed universe, no operational entitlement/authorization, zero allowance, A/B/C locked |
| `/health/research-readiness` | 200 REPLAY_READY | Validated evidence/case, actual registry, explicit deterministic models, committee/risk result; live research and paper readiness false |

Heartbeats and projections expire after 15 seconds. Missing, stale, corrupt or mismatched dependencies fail closed. Mutation methods are 405 and all non-review/non-health/non-projection routes are unavailable in the isolated backend. The browser never sees local runtime paths, licensed raw bodies, credential selectors or credentials.

## Strict universe finding and repair

The legacy radar calls the ledger-backed `current_strict_governed_universe()`. The latest capture attempts were incomplete; older verified captures were stale. Separately, the existing benchmark artifact contains 517 unique members and explicit reviewed `SP500_GOVERNED_IVV` / `NASDAQ100_GOVERNED_IQQ` lineage. Its source mode is `GOVERNED_INDEX_TRACKER_MIRROR`, not direct index membership.

The isolated loader validates the artifact's exact byte hash, schema, complete/strict indicators, source identities, CA provenance, unique members, as-of time and generation. Freshness is at most 36 hours; future-dated or older material is STALE. The actual radar consumes this loader only in isolated mode. The mirror classification is retained in projection and market readiness. No arbitrary ETF/proxy list or fixture can silently become a governed capture. No ticker substitution is inferred; inactive/delisted eligibility remains unknown without current instrument evidence. This is not a repair of the permanent capture pipeline or permission to trade a captured member.

## Evidence envelope

The first adapter accepts existing CONFIRMED Financial Datasets snapshot receipts only. It checks original receipt hash, raw evidence hash/size, normalized receipt hash, instrument membership, source timestamp equality, session date, positive price, request-identity format and explicit internal-replay storage policy. Original evidence/request identity and original one-credit accounting remain intact; replay cost is zero. No historical body is modified.

The normalized envelope binds evidence/trace/parents/session/cycle/generation/release/room/instrument/provider/request/receipt, observed/retrieved/valid-as-of times, HISTORICAL freshness, DIRECT classification, source reference, one permitted price fact, USD unit, unknown confidence, conflict flags, storage policy, cost metadata and content hash. Conflicting instrument/time bindings fail closed; proxy substitution is rejected. Raw vendor bodies never enter model contexts.

Selected source receipt: `a04ca0b633096534ea8e47a7f0cc98d0be3102b95b01e159da4918fb844e9d89`.

Original request/evidence identity: `market-evidence-926583b987960e2ddae72667e75f874469d508dba5f851cf03070cbe5ef3d3c4` (MU, September 9 recovery snapshot). A replay trace hashes topology plus this original identity, distinguishing replay generations without retransmission.

## Routing, challenge and decision

Registry names come from the actual eight-agent `main.AGENT_CONFIGS`, parsed without invoking providers. A price-only case routes to Market Structure Analyst and Skeptic / Red Team. Six unrelated specialists are suppressed with explicit reasons. Relevant registered tags can select optional specialists. Committee is a separate synthesis stage, not an invented ninth registry agent.

Workers receive independent immutable copies of the same normalized evidence and validated memory context. Skeptic receives no primary conclusion. Committee receives explicit prior assessments in a separate context. Outputs require exact evidence citations; unsupported claims and BUY conclusions are rejected. Model-call budget includes committee; worker and committee waits are bounded. Only deterministic acceptance boundaries are implemented here, with no provider or execution tools.

Successful replay events are: OBSERVED → EVIDENCE_NORMALIZED → CANDIDATE → CASE_OPEN → RESEARCH_IN_PROGRESS → CHALLENGE_COMPLETE → COMMITTEE_COMPLETE → RISK_COMPLETE → WATCH → OUTCOME_PENDING. Each event is hash-linked and persisted append-only in one SQLite transaction with the case/decision/evidence result. Analysis failure records failed-closed stage results and forces WATCH; completion labels do not imply a successful investment conclusion. No event can skip committee/risk or enter a paper-authorized state. A future paper-token implementation requires separate single-use/expiry authorization and is not included.

Risk deterministically rejects paper authority and fixes notional/order count at zero. The price-only proof lacks current evidence, thesis, valuation and a validated outcome. Outcome registration is persisted, measurement remains null and no lesson is admitted. Memory retrieval requires an actual hash-valid MEASURED outcome receipt plus a hash-bound human-validated entry. No prose alone is a validated memory.

## Projection and UI truth

Only the publisher writes projections, by reading validated ledger events/results. The backend cross-checks trace, case, outcome, risk, paper, receipt, identities and freshness. The browser independently validates the hash and pins the complete topology/release/runtime/ledger/generation/session tuple. Missing or mismatched data displays UNAVAILABLE; REPLAY never becomes LIVE.

Paper reference balances use decimal strings to avoid Python/JavaScript float serialization differences (`10000.0` versus `10000`). They identify the isolated snapshot source and reconciliation timestamp and explicitly disclaim live-account reconciliation. No animations, character dialogue, orders or fabricated lessons are added. The preview has one polling owner, visible keyboard focus and responsive wrapping.

## Isolated acceptance and rollback procedure

1. Confirm authoritative source and protected PID/port inventory read-only. Work only on the isolated feature branch.
2. Use the locked frontend dependencies. Run focused/adjacent backend tests, frontend tests, lint baseline, TypeScript and normal production build. Build the opt-in preview with `VITE_TRUTH_SPINE_PREVIEW=1 npm run build`.
3. Run `scripts/truth_spine_acceptance.py --help`. Supply explicit source, NEW owner-only root, read-only ledger source, exact receipt/evidence pair, governed universe artifact, validated dedicated runtime template and unused loopback port. Protected ports are rejected.
4. The script copies source/frontend into a read-only package with an exact manifest, copies and binds the dedicated runtime, takes a SQLite read-only backup, preserves a rollback copy, validates the inputs and emits an active topology. No live ledger is initialized, chmodded or written.
5. Actual scheduler/publisher/backend children start with a curated environment and a process-wide no-spend boundary. External sockets, arbitrary subprocesses and credential-file access are denied. Backend mutation routes are denied.
6. Require real health, automatic replay and publication, WATCH, zero orders, radar membership, scheduler-stop readiness failure, restart idempotence, and byte-identical isolated rollback rehearsal. No scheduler/PID/projection output is manufactured by the harness.
7. During the bounded review interval, verify the actual preview in a browser at desktop/medium/narrow widths, no overflow, truthful REPLAY/WATCH, disclosure/focus and zero runtime errors. Backend acceptance alone is never overall GREEN.
8. The script terminates and waits for only its own child processes in `finally`. Confirm zero remaining listener. Failed candidates are retained as diagnostic evidence, not modified into passing packages.
9. After all gates pass, commit/push only the isolated branch; repeat acceptance from the clean committed source. Never merge, promote or change permanent launchd jobs in this batch.

Rollback is an isolated rehearsal: copy the preserved read-only ledger snapshot to a separate file and compare exact SHA-256. There is no authorized permanent rollback/cutover in this batch. A stopped preview is expected at handoff; no bookmark is a permanent entrypoint.

## Evidence index and operator checklist

Each owner-only acceptance root contains `truth-release.json` under `release`, `runtime/runtime-manifest.json`, `active-topology.json`, `service.json`, copied input artifacts, isolated ledger, rollback copy, automatic projection/heartbeats, bounded process logs and `acceptance.json`. Browser screenshots remain outside Git. The report binds release/trace/receipt/evidence hashes and records child cleanup. Never commit these runtime artifacts or licensed raw evidence.

Tests distinguish new contracts from adjacent legacy tests. The repository's exact ESLint baseline (26 errors, one warning) remains separately classified; no rule is disabled here. Date-expired September 9 fixtures are not retimestamped. Permanent source/runtime/provider coverage and investment-workflow readiness remain separate from isolated replay acceptance.

Next batch: review this replay contract and its evidence, then design a separately authorized permanent integration and rollback plan. Live models, current membership/instrument eligibility, measured outcomes, validated lessons and any paper authority require separate gates. Permanent factory status remains YELLOW and unchanged.
