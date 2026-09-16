# Alpha production integration: first increment

Baseline: 3e1ff9d040326caff7d4ce76ff6d8108e8a352fb. The accepted
475-request synthetic rehearsal is retained. It does not qualify OS confinement,
provider entitlements, installation, or production execution.

## This increment

`alpha_session_contract.py` validates an independently pinned session contract,
reviewed XNYS calendar document, and ordered 517-symbol universe entirely in
memory. Date, UTC instants, calendar timezone, validity window, parent bindings,
and false authority fields are checked. Short sessions and winter UTC offsets
are supported as inputs; holidays and actual exchange hours are NOT inferred.
An external calendar reviewer must establish the document's semantics before
supplying its independent hash. Synthetic test dates are not calendar evidence.

Successful validation means CONTRACT_VALID_ONLY. It never means production
readiness or permission to execute. The new module is not wired into the
production runner. Existing MONDAY_ONLY, CLI_LIVE_ONLY and
RADAR_NATIVE_ADAPTER_PENDING guards and legacy assertions remain unchanged.
No request schedule is generated here; a short session must not silently inherit
the full-day 475-request schedule.

The dedicated CI job runs offline unit tests on Python 3.14.7. It launches no
fixture, provider request, native qualification, production service or order.
It does not establish an installed immutable runtime identity.

## Second increment: existing Truth Spine binding

`alpha_session_integration.py` reconciles the separately pinned Alpha session
with `truth_spine_session.parse_session`. It requires matching date, opening
and closing times, and independently expected source commit. Closed, shortened
and historical replay sessions cannot use the normal-session 475-request policy.
The existing calendar's bounded year and closure limitations remain in force.

The versioned candidate preserves one separately bound PILOT preflight and 79
six-batch scans (100/100/100/100/100/17). The final scan ends 5m30s after close,
as in the accepted legacy policy, and must fit the 15-minute reconciliation
window. Short-session request counts are deliberately not inferred.

Reconstruction rejects even rehashed plan changes. The offline stage join binds
every stage to the new date, source, candidate and previous accepted stage hash.
Missing stages block completion; even a complete chain is OFFLINE_COMPLETE,
never production GREEN. Real stage semantics remain the responsibility of
existing governance owners. This is a planning/receipt interface, not a running
Factory adapter. No live receipt converter or new supervisor is introduced.

The old production CLI rejects the new candidate schema. Wiring that schema to
execution remains a later separately qualified increment, and every existing
production admission guard remains intact.

## Third increment: account, runtime and allowance references

`alpha_session_package.py` builds an OFFLINE_INTEGRATION_ONLY package candidate
from independently pinned plan, account, runtime and allowance documents.
It reuses the gateway's required account claim names and amount parser and the
deployment contract's Python version. Every document binds the same source,
session, plan and validity window. Account coverage includes PILOT separately
from the ordered 517-symbol universe; no fallback provider or feed is accepted.

Runtime references bind the manifest, interpreter and platform hashes to the
Darwin/arm64/Python 3.14.7 target. This function performs no disk inspection;
those hashes do not prove installed-file integrity. Account claim hashes likewise
do not prove actual entitlements, retention rights, billing or credential access.
No real account or runtime has been accepted by these synthetic tests.

The allowance binds both account and runtime hashes, exactly 475 requests,
zero enrichment, matching cost units, and 475 times the per-request ceiling
within the stated available balance. Overage, automatic top-up and budget
release remain false. Arithmetic uses bounded decimal inputs and explicit
precision, not floating point or a caller's ambient precision.

Output status is BINDINGS_VALID_ONLY and enumerates the remaining live-evidence,
runtime, confinement, preflight, adapter and installation gates. The package
cannot be passed to the existing runner as an executable package. A later live
admission adapter must verify actual evidence and filesystem/runtime identity;
changing a scope string or accepting these candidate hashes is insufficient.

## Fourth increment: read-only evidence files

`alpha_session_evidence.py` reads only independently approved artifact roots.
Root equality and lexical path checks precede filesystem access. Directory-FD
traversal uses no-follow opens. Exact inventories, owner/immutable modes, single
links, byte limits, hashes and before/after identities reject substitutions.
Reads are bounded to 5,000 files, 64 MiB per file and 256 MiB per root; only
explicit claim JSON (at most 4 MiB total) is retained in memory. Unexpected or
missing files, duplicate JSON keys and changes during reads fail closed.

The existing deployment runtime-manifest schema is reused. Manifest bytes and
listed runtime files are checked, with interpreter and platform-manifest hashes
bound to the candidate. No interpreter is executed. Actual platform files and
running interpreter/module provenance still require the existing production
runtime validator; this check cannot replace it.

Reviewed account claim files must match independent account claim hashes,
account/tier, source, session, symbols, endpoint/feed and the entire account
validity window. Independent reviewers must establish the underlying provider
facts. A matching file or review reference is not proof of its semantic truth.
Unit tests use invented claim documents and non-executable interpreter bytes.

Output is FILES_AND_BINDINGS_VERIFIED_ONLY. It preserves all false authorities
and explicitly requires semantic account review, platform/running interpreter,
OS confinement, live preflight, production lifecycle and execution authority.
This is the read-only portion of admission, not a live execution capability.

## Path to a full market-day observation test

The runnable read-only entrypoint is `alpha_session_preflight.py`. It has no
default roots, execution flag, credential discovery or CLI clock override.
The independently approved input directory contains only an immutable
`admission-input.json`, whose exact raw SHA-256 and byte length are supplied
outside the document. The schema is `iios-alpha-preflight-input-v1`; its fields
are candidate/candidate_hash, plan, account, runtime, allowance, runtime_manifest,
claims_manifest/claims_manifest_hash and package_inputs. package_inputs includes
input_pins, contract, calendar, universe, spine_session, expected and source_commit.
It must not contain `now` or any filesystem-root approval.

On the selected host, the reviewed invocation is:

```sh
python -B alpha_session_preflight.py \
  --input-root APPROVED_IMMUTABLE_INPUT_ROOT \
  --expected-sha256 INDEPENDENT_BUNDLE_SHA256 \
  --expected-bytes INDEPENDENT_BUNDLE_BYTE_LENGTH \
  --approved-runtime-root APPROVED_IMMUTABLE_RUNTIME_ROOT \
  --approved-claims-root APPROVED_IMMUTABLE_CLAIMS_ROOT
```

These are placeholders, not ready-to-run pins. Do not infer approvals from paths
inside the bundle. Account facts must be independently reviewed, not generated
from the test fixtures. No actual selected-host artifacts have been inspected
or qualified by the source CI.

The CLI always reports BLOCKED: verified file/binding checks return exit 2 with
candidate_evidence=FILES_AND_BINDINGS_VERIFIED_ONLY and explicit remaining gates;
failed checks return exit 1 with a fixed sanitized category. Consumers must parse
the report schema and fields; exit 2 alone also denotes argparse usage errors.
Neither result grants execution. Missing inputs are reported without their raw
paths or exception messages. This entrypoint does not execute native validators.

1. Complete and review production runtime/admission integration without relaxing
   the existing live guards; qualify isolation using disposable resources.
2. Independently review real account entitlements, approved costs, current
   universe/calendar and provider freshness; perform a separately admitted,
   bounded live preflight. No broker or order authority is needed.
3. Exercise the actual production lifecycle and Truth Spine/publisher handshake
   in a short controlled observation session, including stop, cleanup and stale
   or missing evidence behavior, on the selected runtime.
4. Independently admit one fresh session package for an entire market day and
   collect actual UTC/monotonic timing, request accounting, generation/health,
   final reconciliation and shutdown evidence. Accelerated rehearsal results
   cannot substitute for elapsed-time evidence.

## Observation controller and billing compatibility

`alpha_observation_adapter.ObservationAdapter` implements the receipt-side
lifecycle controller against the reconstructed short topology. It uses the
existing Truth Spine `ProcessObservation`, UTC normalization and role set.
Three complete observations must agree with the independently pinned parent
launch and startup receipt, including PID, PPID, start time, executable/hash,
exact argv and cwd. `collect_registration` performs exactly three independent
inspection calls without package verification or publication in that loop.
The native inspector/effect binding belongs to the existing Truth Spine owner;
there is no new process launcher, hidden command mode or environment bypass.

ACK eligibility requires registered ownership, exact startup parent and listener
owner. TLS must follow all role acknowledgments. Each of three requests needs a
bound reservation and a second dispatch-window check; a consumed send slot cannot
be admitted again. Completion requires the independent response parent, coverage
and freshness findings. Failure latches the controller closed without releasing
reservations. Cleanup checks every role independently, reinspects identity before
delegating to the existing owner, and never signals an unregistered or changed
child. The owner must still reverify immediately before each signal. Verified
forced exit is distinct from cooperative success. Final reconciliation, publication
and three stable port-clear observations cannot override failed identity cleanup.

Adapter results and receipt-only health projections are permanently
OBSERVATION_ADAPTER_VALIDATION_ONLY, with native semantics, production qualification,
market readiness and execution authority false. Supplied observations and proof
hashes are not self-authenticating OS evidence. The current Truth Spine launcher
still admits only its existing shadow commands; `/health/ready` and its ledger
contract are unchanged. No runnable production effect binding has been granted.
That exact command/root/confinement binding must be independently qualified before
this controller can be connected to production effects; CLI guards stay closed.

`alpha_observation_billing.review_billing` distinguishes PREPAID_UNITS,
METERED_CURRENCY and FLAT_SUBSCRIPTION. All require independently pinned current
cost/billing/rate reviews, exactly three local request slots, an explicit USD
per-request maximum, spending cap and spending headroom. A flat subscription does
not imply zero marginal cost or unlimited requests. Zero requires an explicit
reviewed finding. Prepaid unit availability is checked separately from currency;
non-prepaid models reject invented unit balances. Ambiguity retains the consumed
request and maximum spending reservation with no retry. The currency projection
fits existing package arithmetic without changing its assertions; available
headroom means local authorized spending capacity, not assumed provider credits.
It does not issue an allowance, reserve money or prove account entitlement.

The runtime selector now rejects Windows ARM and incompatible Python ABI wheels
before selecting one deterministic Darwin/arm64 candidate per locked distribution.
Candidate tags do not prove Requires-Python, dependency resolution, signatures,
dynamic linkage or successful imports; all remain build/qualification checks.

## Isolated runtime assembly and observation topology implementation

`scripts/alpha_production_runtime.py` is an importable, non-executing assembler
for an already built/extracted immutable input closure. It does not download,
extract, compile, install or run software. The caller independently supplies the
input document hash, accepted source commit, exact approved input/output roots,
platform-file paths, source-lock bytes and their expected hash. The input schema
is `iios-production-runtime-build-input-v1`. It binds a complete file inventory,
`bin/python3.14`, TLS-bundle path, Darwin/arm64/Python 3.14.7 target, and independent
distribution/build-recipe/toolchain/dependency-artifact/closure-review hashes.
Those references need semantic provenance review; their syntax is not trust.

All lexical checks precede file access. Existing immutable file verification and
platform pin checks retain ownership, no-follow, inventory, size, mode and hash
requirements. Old runtime roots and protected paths are rejected. Dependencies
must match the independently supplied source lock exactly (normalize package
name spelling; never silently omit an extra package such as pip). File copies
use bounded FD-relative reads and exclusive writes; inputs are reverified after
copy. An interrupted output is preserved and cannot be resumed or overwritten.
The output emits the deployment manifest schema directly, with a fresh source
binding, computed dependency inventory, exact output inventory and sealed modes.
It is never a historical-manifest conversion.

The returned assembly result binds the full input hash and manifest byte hash,
reports ASSEMBLED_BYTES_ONLY and leaves all authorities false. Preserve that
result outside the runtime root with its own independently recorded hash. An
assembled manifest is not proof of executable compatibility, complete dynamic
linkage, platform trust, TLS operation, relocation rejection or confinement.
The existing native runtime validator and later source-bound admission remain
mandatory. The unit tests copy deliberately non-executable bytes and confer no
runtime qualification. No real admissible build inputs have been substituted
for missing provenance.

`alpha_observation_lifecycle.py` defines a reconstructed production-observation
**design**, not a running service. It verifies the short package and separately
pinned release/runtime/generation/owner bindings. It reuses the existing Truth
Spine role and probe names, preserves three-sample ownership, receipt/listener
before ACK, TLS before dispatch, no restart/retry, and both pre-reservation and
pre-send dispatch-window requirements. It proposes a sanitized receipt-only
channel with no ledger access; the existing isolated-shadow topology is unchanged.

`alpha_session_integration.offline_observation_join` reconstructs that topology
before joining design-stage receipts. Stage order, independent parents, source,
session, generation, owners, UTC windows, strictly increasing monotonic values,
three-request accounting and request-receipt replay are checked. Failed stages
stop observations while still allowing independent shutdown/publication findings;
primary and cleanup failures remain separate. Partial cleanup cannot make an
incomplete run successful. Design-stage evidence requires OFFLINE_INTEGRATION_ONLY
and DESIGN_TEST_ONLY, never a live or synthetic-native receipt conversion.
Even a complete design chain returns OFFLINE_COMPLETE with native semantics,
production qualification and execution authority false. Proof hashes are references
for future independent verifiers, not proof that ownership or a provider response
was actually observed. The old full-day stage join remains unchanged.

Remaining production implementation is the actual verified launch capability and
receipt publisher/health adapter within Truth Spine, wired to the stricter
short dispatch windows and bounded cleanup. That work must not relabel shadow
services or remove MONDAY_ONLY, CLI_LIVE_ONLY or RADAR_NATIVE_ADAPTER_PENDING
without implemented production admission. OS confinement and native lifecycle
qualification remain separate gates. This increment creates no listener,
subprocess, credential reader, provider request, install or arming path.

The 475-request synthetic milestone is complete. The stages above remain
unqualified until their own evidence passes; this roadmap is not authorization
to install, spend provider credits, launch a market session, or enable trading.

## Subsequent implementation and acceptance

1. Connect the reviewed session identity to a versioned schedule/package and
   final receipt, retaining legacy schema behavior. Bind approved source/runtime,
   calendar, universe, account and allowance independently. No date-only patch.
2. Integrate production lifecycle and evidence with the EXISTING Truth Spine
   supervisor and publisher. Test missing, stale, cross-session and synthetic
   receipts. No second supervisor authority or Truth Spine is introduced.
3. Qualify OS confinement on disposable resources under a separately bounded
   native plan. Python audit hooks are not OS confinement proof.
4. Verify real provider feed/account/entitlement/freshness and approved cost
   allowance, then a separately admitted provider preflight. Connected chat
   provider apps are not local account qualification evidence.
5. Verify the selected installed release, immutable Python runtime, ledger path
   binding, generation, fresh supervisor heartbeat and publisher projection.
   The real backend readiness endpoint is /health/ready; a static frontend
   deployment or generic /health result cannot substitute for it.
6. Qualify production installation, noninterference, rollback and actual session
   operation before separate execution authority. All trading authorities stay
   false throughout this source increment.

## Evidence limits

The original full synthetic run proves accelerated logical execution and a
separate minute pacing boundary. It does not prove a full elapsed-time market
session. CI cannot inspect the user's installed Mac services or protected ledger.
Neither a branch merge nor a GREEN unit-test job establishes those local gates.

## Short observation candidate (offline implementation)

`alpha_short_observation.py` adds a separate, reconstructed contract. It does
not truncate or relabel the 475-request plan. An independently pinned
`iios-alpha-short-observation-window-v1` document supplies the exact source,
exchange date, UTC start, ordered PILOT symbols, three-request maximum and false
authorities. Its pin joins the existing session, reviewed calendar, ordered
517-symbol universe and Truth Spine session pins. No start date/time is selected
automatically. Closed/historical sessions, mismatched calendars, late starts and
windows outside the actual reviewed exchange session fail closed. A reviewed
shortened exchange day can contain this short window; it still cannot use the
legacy normal-day 475-request contract.

The proposed pilot is MU, SPY, XLK, VNQ, TLT, GLD, UUP, IBIT, PFF, BIL. These ten
symbols are observed three times; this is neither 517-symbol coverage nor a full
market-day observation. All requests are Alpha REALTIME_BULK_QUOTES over the
existing HTTPS route. The contract specifies:

| Phase | Relative time | Bound |
|---|---|---|
| Startup | T−60 through T | All runtime/confinement/ownership/ACK/TLS admission before dispatch |
| Bulk preflight | T | Start in [T,T+5s); response before T+25s |
| Observation 1 | T+60s | Same five-second start window and twenty-second request limit |
| Observation 2 | T+120s | Same bounds; no start without accepted preflight |
| Reconciliation | after final response through T+180s | Three independently bound reservations, responses and completions |
| Cleanup/publication | by T+300s | Dedicated 120s reserve, ownership-verified exit and listener clearance |

The selected T must place the entire five-minute window inside the reviewed
exchange session. Authority/account validity must also cover startup and final
cleanup. Maximum request size is 1 MB; maximum observed quote age is 60 seconds,
as in the existing bulk contract. Provider timestamp absence, future timestamps,
stale/partial/duplicate/unexpected coverage or ambiguous billing stops the run.
HTTP success and a returned price never establish realtime freshness.

Three starts per rolling minute remains a ceiling; the proposed start spacing is
60 seconds. Actual UTC and monotonic timings are required; acceleration is not
accepted. No retries, redirects, pagination, fallback, enrichment, rescheduling
or backfill. A missed window is a failed/partial short observation, never a full
day. Interrupted reservations remain consumed or ambiguous until separately
resolved; invalid recovery evidence does not release budget. Owned roles must be
cleaned independently, and an unverified process receives no signal.

Costs are not constants in source: the existing decimal account/allowance checks
require exactly **3 × independently reviewed per-request maximum**, sufficient
available/unreserved allowance, zero enrichment, no overage/top-up and
`released=false`. No subscription or old receipt supplies those missing facts.
All nine existing reviewed account claims and exact runtime/evidence file checks
remain required. Provider payloads stay ephemeral; only the existing sanitized
coverage/timing/failure and accounting receipts may be retained, subject to the
reviewed retention right. Raw quotes, raw bodies, arbitrary provider text and
secret-bearing URLs must not be persisted.

The package schema is `iios-alpha-short-observation-package-v1`; its input bundle
schema is `iios-alpha-short-preflight-input-v1`. The latter adds exactly
`observation` to `package_inputs`, and `observation` to its independently supplied
`expected` pins. The CLI flags, approved roots and input-byte/hash requirements
are unchanged. Full-day bundles retain `iios-alpha-preflight-input-v1` and their
exact existing fields. Mode is selected only by explicit schema, never count.
Both modes still report BLOCKED even when file/binding verification passes.

### Production lifecycle boundary and remaining work

This candidate declares lifecycle acceptance requirements, not a new supervisor
or an executable capability. The unchanged production runner still enforces
MONDAY_ONLY, CLI_LIVE_ONLY and RADAR_NATIVE_ADAPTER_PENDING and rejects this
package. `truth_spine_service.configuration` currently admits isolated-shadow
topology, while its publisher depends on validated ledger inputs. Do not invoke
that path as a substitute for a ledger-free real-provider observation. The
existing Truth Spine session supervisor/health interfaces and OS process-identity
inspector are the integration points for a later reviewed adapter. Required
bindings include selected release/runtime, session, generation, scheduler and
publisher ownership, `/health/ready`, immutable receipt parents and shutdown.

Replacing a pending guard requires a verified production admission adapter and
qualified confinement. Python audit hooks and prior synthetic receipts are not
that proof. A later execution proposal must bind accepted source, runtime,
platform, TLS, exact provider address, reviewed account claims, unreleased then
explicitly authorized cost cap, roots/ports, startup/stop owners and T. No such
authority is generated by this module. Short-observation acceptance must precede
a separately authorized full-day package; the latter retains its 475-request
accounting and requires actual elapsed-time evidence.

Fresh-runtime preparation must use independently pinned, admissible toolchain
inputs, not a relabeled historical package. The historical runtime builder and
production immutable-runtime manifest have different schemas. Ownership and
non-group-writable input checks remain mandatory; missing build provenance or
rejected inputs must be resolved before assembly. Test-runtime bytes and source
CI do not establish a selected production runtime.

## Separate runnable observation process binding

`alpha_observation_launch.LaunchOwner` now implements the previously missing
**receipt-only process effect binding**. It launches the fixed
`alpha_observation_child.py` command, through the pinned system sandbox launcher,
for the existing scheduler, publisher and backend role names. It does not call,
rename, widen or relabel the isolated-shadow launcher. Its child is a new service
component; it never reads a ledger or runs the market-data scheduler.

The independently supplied capability hash, approved roots, source and topology
parent must match before filesystem effects. Canonical lexical checks precede
file access. Exact immutable runtime/release/control inventories are checked
before launch and once before each registration. Fixed argv, isolated Python,
empty-by-construction credential-free environment, closed stdin and bounded
nonblocking pipes prevent arbitrary launch commands or raw-output retention.
The output root and receipts use exclusive creation and existing FD-relative
publication/identity checks. An interrupted root cannot be resumed.

A child publishes startup before waiting for ACK, so registration never waits on
an ACK-dependent event. The parent collects three complete independent Truth
Spine process observations without repeated package admission inside the loop.
PID, PPID, UTC start, executable/hash, exact argv/command and cwd must agree.
Ownership is retained before publication, permitting cleanup after a publication
failure. Exact startup parent and listener-owner verification precede ACK. The
backend exposes only one fixed loopback TLS component response. It is not a
production health endpoint, quote, provider receipt or external transport.

The descriptor binds one monotonic-nanosecond clock origin and startup/stop/final
deadlines. Startup is at most120seconds, component total at most900seconds, and
at least120seconds remain after stop for cleanup. Cleanup independently reinspects
each role before publishing its cooperative stop. Each wait is bounded to30seconds
and the remaining global deadline. This binding has no terminate/kill fallback;
unverified or surviving children remain UNVERIFIED. Exit code, hash-bound child
exit receipt, listener census and three stable port-clear observations are all
required. Clear ports cannot override failed ownership or exit verification.

Every result is permanently OBSERVATION_LAUNCH_COMPONENT_ONLY, with production
qualification and all authority fields false. Actual confinement, runtime imports,
OS inspection, TLS and cleanup still require a separately approved selected-host
qualification. A capability digest identifies a reviewed invocation; it does not
prove the semantics of its runtime, policy or account. No component receipt can
satisfy the existing live CLI, synthetic-native or production package contracts.
The old production guards and the accepted475-request rehearsal are unchanged.

This closes the source-level receipt-process launch mechanism, **not the real-data
production admission/dispatch bridge**. Connecting a qualified controller to three
live gateway requests still requires actual account/runtime/confinement/preflight
proofs, explicit credential/cost authority, and a separately reviewed integration
that preserves the current production guards. It cannot be obtained by changing
this component scope or interpreting its TLS response as provider readiness.

## Reviewed qualification boundaries

These corrections distinguish an observed failure, its attributable cause, and
acceptance. None supplies runtime, account, confinement or execution authority.

### Attributable denial

`EACCES` and `EPERM` are observed access failures, not proof of Seatbelt enforcement.
The disposable probe must report `OBSERVED_ACCESS_DENIAL_UNATTRIBUTED`; UNKNOWN,
exit 65, SIGABRT, timeout and connection refusal never establish policy success.
For dummy regular-file comparisons, independently bind the same executable,
argv, cwd, principal, environment, host, operation and target identity/metadata.
Show an allowed baseline before the confined trial. For exclusive writes use
separate, identically prepared, independently inventoried targets and account for
that difference; do not reuse a now-existing baseline destination. The trial must
bind its own PID/start and profile hash. Record DAC/ACL/flags and any observable
other access-control context; unexplained differences prevent attribution.

A denial claim additionally needs an independently reviewed OS-policy observation
that attributes the denied operation to that process and policy. Bind actual
capture identity, timestamps, operation and target; a hash of self-reported JSON
or a synthetic event is insufficient. No supported bounded collector or native
attribution evidence is currently qualified. A report-consistency checker is not
such a collector. No unrestricted logs, unrelated process inspection or raw
sensitive diagnostics may be gathered to fill the gap. Do not create unconfined
DNS/public-network comparison traffic. Network/process restrictions remain
UNQUALIFIED without equivalent attributable evidence. No production guard changes.

### Final-destination relocation

The assembler correctly returns `ASSEMBLED_BYTES_ONLY`. It does not establish
working relocation. Qualify the immutable interpreter at its exact final runtime
destination, not the staging executable. Resolve every Mach-O dependency/load
command and rpath against that destination; reject staging and historical
framework references, unresolved edges, and unapproved fallback paths. Include
extensions and dependencies not exercised by the initial import set.

Under a scrubbed environment, invoke only the final interpreter with isolated,
no-bytecode options and a pinned observation script. Bind actual executable,
prefix/base-prefix, search paths, stdlib/dependency/extension origins, loaded dyld
images, TLS provenance and exact approved OS dependencies. No PYTHONPATH or DYLD
repair may conceal a relocation failure. Verify unchanged closure inventories
before and after. Static closure review and actual native observation are both
required; a consistent supplied report proves neither completeness nor execution.
A successful staging import cannot substitute for this gate. Testing without the
newly owned staging tree must be separately pinned and must not modify or hide
system/historical runtimes. No runtime has passed this native gate yet.

### Build-control bootstrap

Before running extraction, assembly or relocation Python scripts, independently
qualify the build-control interpreter, stdlib, shared libraries, loaded helpers,
script bytes, ownership/modes and platform/dependency closure. Verify vendor and
bootstrap provenance independently of that interpreter; it cannot self-certify
its own admission. A main-binary SHA alone is insufficient. The observed installed
framework interpreter is group-writable and lacks this reviewed closure. It is
not currently admitted for assembly. Existing offline test use does not confer
that permission. Do not chmod, relabel or copy rejected inputs into compliance.

Missing input: a separately reviewed build-control closure/provenance manifest
with a trusted verifier/bootstrap and applicable host identity. If a different
bootstrap distribution is proposed, identify its exact acquisition and trust
chain for review; it is not implicitly included among the existing 41 artifacts.
Public acquisition, private assembly and native qualification remain separate
phases. Assembly stops before any Python build script until this gate passes.

### Remaining real-data connection

The short-observation planner/preflight is not an executable gateway package.
`alpha_market_baseline.verify_plan` rejects its schema. The public gateway path
is `provider_gateway_qualification.qualify` -> admission/runtime validation ->
`alpha_session_execution.execute_day` -> per-request `_qualify` -> transport.
The private bulk permit and both reservation levels cannot be bypassed. The
current `NativeHTTPS` does not forward a short-window guard to the shared HTTPS
`before_request` hook. The shared wire implementation already has that hook; no
new HTTP implementation is needed. The scheduler's expiry check is not the
short plan's five-second dispatch cutoff.

The missing implementation is a positively admitted, separately versioned live
short-session package and controller-to-gateway execution entrypoint. It must
bind the selected source/runtime/generation, session/calendar, exact ten ordered
symbols, three rows, account/retention/billing evidence, unreleased allowance,
explicit credential/cost authority, roots, actual-time dispatch cutoffs and
qualified native confinement/lifecycle evidence. Recheck time before session and
request reservation and immediately before HTTP send; preserve consumed or
ambiguous reservations and zero retries. A late slot fails, without backfill.

Use a separate production owner/worker admission path reusing reviewed ownership
primitives. The receipt-only `LaunchOwner`, its child and shadow service remain
component-only. Do not widen their scope or remove `CLI_LIVE_ONLY`,
`RADAR_NATIVE_ADAPTER_PENDING` or the old runner's date guard. Final acceptance
must reconcile three actual requests and receipts with owned startup, health,
publication and cleanup; a dummy TLS response or synthetic receipt is inadequate.

Concrete proposed bridge review scope (not implemented or executable here):

- New `alpha_observation_admission.py` and `test_alpha_observation_admission.py`:
  independently pinned production capability/package, account and execution gates.
- New `alpha_observation_execution.py` and `test_alpha_observation_execution.py`:
  production owner/worker entrypoint, scheduler/gateway connection and final join.
- Existing `alpha_market_baseline.py` / `test_alpha_market_baseline.py`:
  explicit additional short-live plan version; preserve all legacy reconstruction.
- Existing `provider_gateway_live_contract.py` / `test_provider_gateway_live_contract.py`:
  bind per-request admission to the separately capped three-row session.
- Existing `provider_gateway_qualification.py` / `test_provider_gateway_qualification.py`:
  reviewed runtime closure, request-reservation cutoff and existing bulk permit.
- Existing `alpha_session_execution.py` / `test_alpha_session_readiness.py`:
  short-window session-reservation cutoff and scheduler completion/recovery.
- Existing `provider_gateway_transport.py` / `test_provider_gateway_transport.py`:
  admitted short-window check forwarded to the existing pre-send hook.
- This document and `.github/workflows/alpha-session-contract.yml`:
  exact new contract tests and component/production status separation.

All Python paths above are under `BACK END/backend`. No shared HTTP-mechanics,
Truth Spine, credential-selector, shadow-service or confinement-policy edit is
proposed. If implementation proves another path necessary, review that scope
before editing. This is source integration scope, not real-provider authority.
