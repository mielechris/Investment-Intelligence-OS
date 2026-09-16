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
