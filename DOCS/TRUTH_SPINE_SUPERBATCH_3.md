# Truth Spine Superbatch 3 — isolated disabled integration

Base: `664e88f86fcd064b4ba3044deda832dd3facfb08`. This is an unstaged source
candidate, not an installed or approved permanent release. Permanent production
remains YELLOW. No promotion or operational authorization is implied.

## Boundary

`truth_spine_authority.py` defines the hash-bound, UTC-expiring disabled document.
All ten capabilities are false. Missing, malformed, expired, mixed-release or
incorrect-owner bindings are denied. There is no activation implementation.
The 41 source entry guards are enumerated in `truth_spine_entrypoints.json`.
Tests execute their actual guard statements ahead of a side-effect tripwire.
Superbatch 3.2 additionally imports the real Financial Datasets module and checks
application/discovery paths under a no-spend audit boundary. No real provider or
credential operation is permitted.
The installed observer additionally denies outbound connections, subprocesses,
dynamic-library loading and credential-file access with a process audit hook.
These are defense-in-depth boundaries, not a sandbox against hostile host code.

This does not retroactively disable already-running legacy binaries, wrappers,
other checkouts or independent LaunchAgents. Existing positive execution tests
must not be interpreted as proof that those installations obey this candidate.

## Topology and stores

`iios-readonly-topology-v2` separately binds release, runtime, interpreter,
dependencies, operational/historical/event ledgers, executor generation, source
cycle, evidence receipt, case namespace, projection generation, publisher,
frontend, owner identities and rollback parent; the authority document is
separately file-hash-bound. Explicit source paths are mandatory. Empty, corrupt,
unowned, symlinked or hash-mismatched sources are rejected. Live WAL-bearing
ledgers require a consistent read-only SQLite backup before ingestion.

L7/L8 adapters preserve source/object IDs, content hashes, original clocks and
schema references. Namespaces include the source snapshot hash; identical bare
IDs from separate stores are never merged. Retained executor receipts are bound
to evidence hashes. Archive file inventories are validated. Only browser-safe
9I summaries are admitted; raw private strategy is not a browser input.
Historical, REPLAY, SIMULATED, NARRATIVE, STALE and UNAVAILABLE are not relabeled
as current observations. Universe captures retain original member hashes,
timestamps, provenance and predecessor references; tracker membership is never
claimed as direct official index membership.

Canonical observer writes are confined to an independent event ledger. They
never write the operational ledger. Replay is idempotent and payload collisions
fail closed. Memory classifications remain distinct; validated lessons require
bound case, evidence, decision, measured outcome/horizon and human admission.
There is no automatic memory promotion.

## Superbatch 3.2 source-review repairs

The `CredentialProvider` protocol no longer evaluates authority at import time.
Application import no longer loads `.env`. Invocation remains deny-only: `fetch`
accepts explicit document/binding/release/owner inputs but cannot grant permission;
direct `_request` and both TLS transmission entrypoints also deny before trust,
credentials, accounting or network activity. TLS transport is one additional
production-file repair because a direct caller could otherwise bypass `fetch`.
No new provider implementation, default grant or authority bypass is introduced.

Evidence provenance and retention are separate. `evidence_classification` and
the compatibility `classification` field preserve the original recognized label;
`record_origin`, `retention_context`, `classification_basis` and the existing
three clocks describe storage/context without changing provenance. Missing
evidence classification is UNAVAILABLE, never inferred HISTORICAL. Unknown,
malformed or contradictory evidence labels reject normalization. Schema-bound
executor state/plan and session archive `classification` fields describe session
type, not evidence: their reviewed enums remain in `session_classification`, and
they do not manufacture an evidence label. Missing evidence remains UNAVAILABLE.
The publisher re-derives adapted records from pinned original bytes before using
persisted classifications. Re-sealing an upgraded event-row hash is insufficient.
The Museum displays classification counts separately from retained-record counts.

`MemoryTrustAnchor` is an explicit **bootstrap trust input**, not a field accepted
from the submitted lesson. It pins an already independently reviewed source
registry file hash, topology identity, authority identity and admission-policy
version. Its containing directory must be owner-only 0700; registry/original
files must be owner-owned regular 0400/0600 files with no symlink path components.
No registry builder, operational registry installation or browser admission route
is provided. An operator must independently authenticate these pins before a
future consumer can configure the verifier. This batch does not establish such
an operational registry or claim historical records are validated memory.

Registry schema: `iios-memory-source-registry-v1`. Each admission identity binds
fixed original record, case, evidence receipt, decision, committee, risk decision,
measurement definition/horizon, outcome receipt and admission receipt files plus
raw evidence, all by relative path and SHA-256. Every object binds source-store
namespace, original source-object identity, canonical case identity, generation,
instrument, evidence classification, topology and authority. Canonical case
identity is the hash of `{store, object}`. Outcome/decision/measurement/committee/
risk/admission identity and content-hash links must reconcile independently.
Raw evidence must match the original receipt hash. Only original HISTORICAL or
LIVE_VERIFIED chains can qualify; simulations, narrative, replay, reviews and
unresolved provenance cannot be wrapped into a validated lesson.

`admit_lesson` compares submitted objects byte-for-byte with those independently
pinned originals. It returns INSUFFICIENT_PROVENANCE if the registry is absent or
any binding differs. It is a read-only eligibility verifier, not a memory writer:
rejection, restart and concurrent calls create no partial or duplicate admission.
Persisting validated memory remains unauthorized. Concurrent verification is not
a claim of a deployed transactional admission service.

Regression clearance must not be inferred from focused tests: legacy provider
tests expecting invocation without the deny-only authority contract remain
substantive failures until separately reconciled without weakening that boundary.
No expired cost fixture may be retimestamped to make the suite pass.

## Publisher and acceptance

The packaged scheduler ingests persisted copied records; the packaged publisher
reads that ledger and the hash-bound executor/paper state. The acceptance runner
does not write a projection or heartbeat. Each producer owns one exclusive lock.
Readiness validates package and input hashes, owner heartbeat, lock/PID binding,
fresh publication and projection equality to persisted input. Liveness is not
readiness. Market readiness stays 503. Historical review readiness is not live
research readiness, and SESSION_CLOSED is not INSTALLED_DISABLED.

The Museum adapter is additive, with a separate isolated preview. It does not
replace artwork, case routing, layout, frozen V7.6 behavior or port 5176.
Dynamic universe counts and separate source/event/publication clocks are shown.
The 15-step target Day Trading contract ends NO_PAPER_AUTHORITY / ABSTAINED.
No provider/model adapter is activated; unimplemented providers remain so.

`scripts/truth_spine_integration_acceptance.py` prepares a new owner-only root
from explicitly supplied retained sources. `scripts/truth_spine_integration_runner.py`
starts only its own packaged observer roles on an isolated port, tests duplicate
owners, stale publication, restart idempotence and recovery, and closes its
processes after a bounded review interval. A preparation is not acceptance.
Logs, raw copied evidence, DB snapshots, bundles and screenshots remain outside
source control. Full original-store hashes and local paths are private evidence.

## Separately reviewed deployment allowlist and cutover proposal

No deployment is performed by this batch. A later approved cutover must inventory
and hash the actual current service files immediately before use; PID or pathname
history is not sufficient authorization to signal a process.

The explicit later scope is:

1. A clean immutable release containing the reviewed backend authority/adapter/
   observer modules, guarded entrypoints, runtime/dependency inventory and the
   compatible frontend adapter. No mixed-checkout imports.
2. New hash-bound topology and disabled-authority configuration, explicit L7/L8
   read-only sources and a separate canonical observer event-ledger root.
3. The scheduler and publisher LaunchAgent configurations and their exact
   executable entrypoints, after ownership/manifest review. Bind independent
   owner identities; prohibit duplicate old/new owners.
4. The mutable legacy `9b_cycle_child.py` wrapper and the batch9b
   `iios_paper_trading_runner.py` launch path: do not patch them in place as an
   undocumented workaround. Preserve byte-exact rollback copies and replace
   their launch configuration with immutable authority-gated entrypoints only
   under separate authorization. Remove the independent execution default.
5. Any independently running credential/model wrapper must be inventoried and
   disabled or replaced under separate owner approval before claiming global
   disabled authority. This source candidate cannot make that claim for it.
6. Museum compositor configuration only after adapter parity review; preserve
   permanent 5176, artwork, case routing and rollback assets.

Sequence: record protected identities and consistent source snapshots; build and
verify the clean release; validate byte-exact service/configuration/state rollback;
rehearse restoration in isolation; stop only separately approved old owners and
prove teardown; select immutable configuration; start one owner per role; verify
readiness, authority denial, Museum parity and historical preservation. At the
first failed gate restore prior binaries/configuration without rewriting original
ledgers or evidence. Do not proceed until every mutable bypass is accounted for.

Missing or unprovable input, ownership, source provenance or rollback evidence
is a stop condition, not permission to repair permanent production.

## Superbatch 3.3 — offline compatibility and recorded evaluation clocks

The prior Expansion Wing result (6 failures, 105 errors) has two root causes:
75 authority errors plus one singleflight assertion are legacy tests invoking
newly denied side effects; 30 cost errors plus five later-stage assertions
cascade from a fixture using real time after its original cost evidence expired.
The accepted base reproduces the cost failures, but not the new authority errors.
Its separate build-identity failures are missing local frontend dependencies,
not production or candidate regressions. No fixture dates were retimestamped.

`expansion_wing/test_authority_fixtures.py` provides explicit per-test offline
boundary scopes. Only individually decorated test functions can request mocked
provider or credential boundary evaluation. Context-local scopes expire at test
exit, including inherited worker-thread contexts. Explicit authority documents
still pass through the unchanged production validator. There is no paper, model,
broker, promotion or operational-ledger permission in the fixture. An irreversible
audit hook additionally rejects external/protected network targets, Keychain,
credential files, operational commands and writes outside isolated temporary
roots. This module is test-only and excluded by the existing package test-file
filter; no production module imports it. Mock counters are not operational calls.

Two obsolete adapter assertions now explicitly require AUTHORITY_MISSING before
invocation. Read-only capabilities and URL calculations remain available without
authority. Positive tests retain their response, transport, accounting, tamper
and singleflight assertions under their individually named offline scope.
Production `require_capability` remains deny-only, missing authority denies,
environment/arguments cannot grant permission, and legacy paper execution flags
remain denied. This is test compatibility, not operational authorization.

Cost evaluation has an explicit UTC clock interface. Production defaults to real
UTC system time. Corrected-generation reselection captures one time and prohibits
an injected clock in OPERATIONAL mode. Tests use the original September 9 03:00
UTC fixture window with explicit REPLAY classification in canonical isolated
temporary roots. REPLAY/HISTORICAL cannot target the fixed operational root.
The existing caller-captured `now` argument on the pure cost validator remains
compatible; the side-effecting operational reselection always obtains its own
system time. No CLI or environment clock override was introduced.

New supersession receipts use `iios-operational-market-generation-supersession-v2`
and hash-bind evaluated_at, evaluation_classification, original observed_at and
expires_at, cost-contract hash and canonical plan identity. Validation requires
the recorded evaluation to lie inclusively inside the original validity window.
Legacy v1 receipts remain byte-identical and valid under their original contract.
Restart retains an existing receipt; it does not update its recorded evaluation
time. A historical receipt does not make expired evidence operationally current:
the production transition still independently checks current cost validity.

New tests cover immediately before/at/after expiry, future/naive evaluation,
ambiguous clocks, operational injected-clock rejection, fixed-root replay
rejection, environment independence, single clock capture, receipt restart byte
preservation, tamper rejection and legacy receipt compatibility. Authority tests
cover per-test scope restoration, absent/invalid documents, unlisted capabilities,
real-boundary rejection and environment non-grants.

Source-only validation: Expansion Wing 776 tests, zero failures/errors, one
existing skip; focused Truth Spine/authority/memory 98 passed; backend discovery
1,403 objects with zero import errors; frontend/Museum 130 passed. TypeScript,
normal and isolated Vite builds pass; the reviewed ESLint baseline remains 26
errors and one warning with zero new violations. Retained-source replay and a
separate-process restart preserve 9,738 unique records and original source hashes;
the isolated replay rollback preserves bytes, sizes, ownership and modes.

This checkpoint does not install a shadow runtime, deploy an observer, authorize
an operational session or certify permanent production. Permanent remains YELLOW
and unchanged by this source batch. Whole-system audit may resume after the
source checkpoint; installation and promotion still require separate approval.

## Superbatch 3.5A — source-only shadow runner hardening

Scope is the runner, its focused test module and this document. No observer
authority, evidence classification, memory semantics, service implementation or
frontend asset changes are included. This checkpoint is not a port-5290 rehearsal.

The prior runner trusted a stored PID, removed it before confirmed termination,
and allowed one shutdown exception to abort all remaining cleanup. It tested
only scheduler duplication and restarted the scheduler without first proving
readiness failure. The replacement keeps immutable fingerprints containing role,
PID, parent, OS-observed start time, exact command/argv, manifest-pinned executable
identity, working directory, shadow root, backend port, creation timestamp and
runner identity. macOS inspection uses bounded ps/lsof commands without a shell
or environment dump; tests inject an inspector, not a production CLI override.
Every graceful/forced signal requires an independent matching inspection.

Unverified startup records are retained separately from accepted fingerprints.
Missing or mismatched identity means no signal, retained unresolved ownership,
PROCESS_IDENTITY_MISMATCH and RED. A reaped Popen child with its previously
verified fingerprint is recorded as already exited, without signaling a possibly
reused PID. Graceful termination has a maximum 30-second wait; timeout is recorded
and requires full reinspection before one force-stop and another bounded wait.
Only confirmed exits leave the active registry. Completed fingerprints remain.

Cleanup attempts every child in reverse start order, independently closes each
log, and always attempts the port check. Only connection refusal proves the
loopback port clear; permission errors/timeouts cannot produce GREEN. Primary
and cleanup exception categories/types are preserved without unrestricted error
messages. Acceptance and incident reports use owner-only sibling staging files,
file fsync, atomic replacement and directory fsync in the supplied isolated root.
Both output attempts are independent; any persistence failure is RED and triggers
a best-effort minimal emergency incident. Repeated cleanup is idempotent. An
unresolved child, unclosed log or unproven clear port prevents clean shutdown.

Duplicate checks now cover scheduler, publisher and backend. Live contenders
use the same fingerprint contract; fast already-reaped rejected contenders are
not accepted owners and never receive a signal. Rejection must preserve the
verified original owner, lock bytes and canonical unique/event counts. Existing
service lock files contain PID bytes; those bytes are checked together with the
runner's independent OS fingerprint, not represented as a new lock-file schema.
Any contender whose identity cannot be verified remains a fail-closed incident.

Focused proofs use fake children, temporary leases and an ephemeral loopback bind
(port zero, never 5290). Actual Lease/probe/heartbeat logic rejects duplicate
scheduler/publisher ownership, stale heartbeats and ownerless locks; restart can
acquire once after the original lease closes. Backend second-bind rejection
preserves the original listener. The scheduler health test uses the real health
and ownership probes with fixture-only unrelated package/projection inputs:
ready 200 → verified stop → 503 → new fingerprint/heartbeat → 200; market
readiness stays 503 throughout. It does not repair a database or projection.
The runner requires the same transitions and unchanged event counts in a later
separately authorized installed-runtime rehearsal.

Adversarial cases include command/start/root/executable/parent mismatch, missing
process, inspection failure, timeout/reverification, terminate/wait/kill failure,
force-wait timeout, one/all child failures, partial startup, KeyboardInterrupt,
log and port failures, atomic-write failure, emergency-write failure, repeated
cleanup, duplicate ownership disturbance and old-fingerprint rejection after
restart. No mismatched or unverified process receives a test signal.

Validation for this source candidate: 48 new runner tests; 158 focused runner,
Truth Spine, integration, authority/memory and compatibility tests passed;
Expansion Wing discovery/run: 776 tests, zero failures/errors, one existing
opt-in Keychain skip; full backend discovery: 1,451 objects, zero import errors.
Python 3.14 compilation, whitespace/diff, secret/credential/personal-path,
authority-bypass, symlink and artifact checks must pass before checkpoint.
Existing resource warnings in the combined legacy suite are not new failures.
Frontend/Museum rerun is not required: no shared/frontend contracts changed.

Operational provider/model/credential/broker/paper activity for this source batch
is zero. Permanent production remains YELLOW and unchanged. No historical shadow
root is created, no port-5290 rehearsal is run, and no merge, deployment or
promotion is authorized. The new commit is the source-candidate identity for a
separately authorized repeat of Superbatch 3.5; source test success is not an
installed-runtime acceptance claim.

## Superbatch 3.5B — frontend provenance and reproducibility

### Verified mismatch

Classification: STALE_RETAINED_ARTIFACT and SOURCE_MISMATCH. The retained
193,773-byte DeTs9eDC JavaScript lacks three changes already present in accepted
TruthSpineIntegrationPreview.tsx: retention_context/classification_counts
validation, the Original evidence classifications section, and the change from
"historical records" to "retained records". There is no extra current application
logic in that older bundle. It must not substitute for the accepted source.

An in-memory forensic build removing only these changes reproduces the retained
SHA-256 85d14810fe036c32e6820800b620f2c92b251fc33ed503fe74c02c8f0d4717f3
byte-for-byte with the same toolchain. Reconstructed earlier TSX snapshot hash:
b7ead6fc423f85f65fd64ecc6cec4cc89115ef98a8e771238fda65bc3ef2036a.
Current TSX hash: d1bb0728584c83b8da3983fd0d424b4b69ec0ea3ee05cd0a7be2cf8f9f9deaef.
This reconstruction proves the source delta; it does not invent an original
build timestamp/commit. The retained artifact has no provenance manifest, and
the file first entered tracked history with the newer source at 4e38f582.

Module observations identify the two application files
src/TruthSpineIntegrationPreview.tsx and src/TruthSpinePreview.css, the HTML entry,
React/React DOM production and JSX-runtime modules, scheduler production modules,
and Rolldown/modulepreload virtual modules. The old/new library prefix is
identical; CSS is identical. Formatting is not used as equivalence evidence:
the isolated old-source reconstruction matches the complete original bytes.

### Canonical build inputs

Node v24.19.0, executable SHA-256
1f08f0e5b8d9a0136c6219f4cea4d96e0ff64869ce0dda6dd6a35; npm 11.17.0, CLI hash
8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7.
npm identity is read from installed files, without loading npm/user registry
configuration or making an installation request. Vite 8.2.2, Rolldown 1.2.5,
Oxc minification, @vitejs/plugin-react 6.1.0, TypeScript 6.0.3, React/DOM 19.2.8.
Every installed dependency code file and package identity is recorded; normal
internal .bin links are verified then copied as regular files. Environmental
.tmp/.vite/.vite-temp/.cache/__pycache__ and tsbuildinfo caches are excluded
explicitly, never used as build input. No network dependency installation occurs.

package.json hash: 11b8111e0ac514cf8ae1129dcdb6cdabeaab26f6fa10dbc1f897f44d84789c23.
Lockfile hash: 71dd50350c8b6eb4cb8723b0da9547bcdafbb7718e6d875cd31be18ca3936ceb.
Vite config hash: c1b72b6ca4860b89026c4af90cc3c655dfbbec10efb2048bb04326cfacba6d4c.
All three tsconfig hashes and the complete 235-file tracked frontend inventory
are included in each build input manifest, along with the builder/driver hashes.

Production mode, NODE_ENV=production, VITE_TRUTH_INTEGRATION_PREVIEW=1 are fixed;
all other VITE variables are absent. Locale LANG/LC_ALL=C and timezone UTC are
fixed, with no inherited environment, .env file, credential or account inputs.
The config loader is runner (no .vite-temp source-checkout writes), base /review/,
sourcemaps disabled, targets chrome111/edge111/firefox114/safari16.4/ios16.4.
Each build starts from a new temporary root and copied source/dependencies, with
no previous dist or build cache. Outputs are not normalized or rewritten.
Different working directories and ambient locale/timezone values produce exact
byte equality. A separate CRLF-only TSX experiment also produces identical JS;
the provenance still binds actual source bytes and rejects modified source.
No timestamps/generated nonces or developer paths appear in the six outputs.
Date.now in the application is runtime freshness validation, not build metadata.

### Accepted six-file frontend

| Relative file | Bytes | SHA-256 |
| --- | ---: | --- |
| assets/truth-integration-C1hHYWhF.js | 194423 | e9dffd6ba26c0acab73f57fa47e9a70962b4defc6240df652595b832e64b8529 |
| assets/truth-integration-DufHPXjH.css | 722 | 56246f5e1e6ae698f1e40c42ab279f663929d28cd9463dde1126a186248c3021 |
| favicon.svg | 9522 | 61bc9a161de58248288e6905425d7180f0624c2865007b97d763fdac12043a66 |
| fixtures/expansion-wing.json | 5932 | 62fedbaf0c266e776bef7ce3a8e3f7c724c0e9dc5ae89e87450014663397ae26 |
| icons.svg | 5031 | b45fa506195cfcdef406ba9f0c77b36ddc1a7c224040926ec70abc2fdea7b93a |
| truth-integration.html | 417 | 80dfd0837168d174888334be2674984ffa6fcc9c3e32099498a2d859ff476c59 |

Aggregate frontend hash (SHA-256 of sorted path/bytes/sha256 inventory serialized
with sorted JSON keys, compact separators and a trailing newline):
37a28d8fdef8d09654d4716702ec2c19b944f23f15f717851452753aceb80c4f.
Generated files are retained only in temporary build roots, not committed.

### Package contract and later procedure

`truth_spine_frontend_provenance.py` builds/verifies
iios-truth-frontend-build-v1. Inputs bind the exact expected source root/commit,
raw source inventory, package/lock/config/tsconfig hashes, Node/npm identities,
complete dependency inventory, fixed policy and builder hashes. Outputs bind
all six files, sizes, hashes, HTML references and module/config observations.
Wrong/missing/mutated/unmanifested assets, stale dist, extra old JS, maps and
absolute developer paths fail closed. Recomputed child hashes cannot replace
the independently supplied provenance-manifest pin or source-root binding.

The preparation script requires a clean committed checkout and these additional
explicit arguments: --frontend-build, --frontend-input-hash and
--frontend-manifest-hash. It validates them BEFORE creating a shadow root or
binding a port, then copies only the proven build/dist. There is no source/dist
fallback. The outer release embeds the complete provenance, source inventory,
frontend input/content hashes and source_state=CLEAN_COMMITTED_SOURCE. The
existing packaged topology validator reconciles that attestation to the installed
file list without consulting the developer checkout. Old packages without this
contract are not new accepted candidates; no running service is changed here.

After checkpoint, use the builder CLI twice with the new full commit and separate
new /private/tmp/iios-frontend-build-* roots. Compare input manifests, module
observations and all six output bytes. Retain the two manifests and use one
verified build root plus its printed input/manifest hashes for a separately
authorized Superbatch 3.5 preparation. The manifest/input hash changes with the
new commit; the six frontend hashes above remain reproducible. Recalculate the
whole backend/frontend prospective package identity after that verification.
Do not reuse the old 243-file digest as an acceptance requirement.

Source validation includes 34 focused provenance tests (including actual dual
cache-free builds), 192 combined Truth Spine/package/runner/authority tests,
130 frontend/Museum tests, 776 Expansion Wing tests (one existing opt-in Keychain
skip), and 1,485 backend discovery objects with zero import errors. TypeScript,
production Vite builds, the existing build-identity matrix, Python compilation,
diff and safety scans pass. ESLint exact baseline remains 26 errors/1 warning,
zero new violations. No production source permissions, credentials, evidence,
authority semantics or permanent service configuration are modified.

This is source-only reconciliation: no historical shadow root, port-5290
rehearsal, full-day operation, deployment or promotion. Permanent remains YELLOW.
