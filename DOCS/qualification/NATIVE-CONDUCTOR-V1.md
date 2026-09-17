# IIOS Native Qualification Conductor v1: architecture and readiness

Status: source core and offline contracts implemented; native integration incomplete.
This is not a qualified end-to-end Mac conductor. A passing preparation CI result
covers source tests only. The manifest compiler refuses execution when any of the
four native adapter bindings is missing. Do not replace those bindings with old
commands: consumed execution roots, fixed budgets, and legacy failure reductions
make them incompatible.

## Ordered state machine

| State | Operation | Effect/retry policy |
| --- | --- | --- |
| SOURCE_AND_CI_ADMISSION | Manifest, source inventory, exact-commit preparation receipt, input and history pins | Read-only; reviewed predicate retries only |
| HOST_AND_TERMINAL_ADMISSION | Exact host, Apple Terminal markers and three TTYs | Read-only; reviewed predicate retries only |
| HISTORICAL_PROCESS_RECONCILIATION | Three observations of registered PIDs; no historical ownership claim | Read-only; reviewed predicate retries only |
| FRESH_OUTPUT_ROOT_QUALIFICATION | Exclusive owner-controlled 0700 payload under the bound parent | Effectful; never retry |
| PRIVATE_RUNTIME_ASSEMBLY | Independently reviewed assembly adapter; bottom-up signing | Effectful; never retry |
| STATIC_SIGNATURE_AND_INVENTORY | Complete independent static verification | Read-only; reviewed predicate retries only |
| FINAL_RUNTIME_ACCEPTANCE | Bounded non-provider runtime acceptance | Effectful; never retry |
| DISPOSABLE_CONFINEMENT_AND_LIFECYCLE | Disposable confined lifecycle and independently verified cleanup | Effectful; never retry |
| EVIDENCE_EXPORT_AND_VERIFICATION | Complete inventory, report and export seal | Effectful; never retry |

The final four native operations require migrated source adapters. Their binding
schema includes the adapter hash, command, input parents, expected outputs,
ownership contract, outer-budget contract, failure protocol and review parent.
No legacy-command fallback or skipped-state GREEN is permitted. Adapter source
is loaded only when its admitted stage is reached.

## Budget and continuation

One monotonic budget has work, cleanup and export boundaries. Every stage receives
the earlier of its stage cap and the remaining outer boundary. Cleanup precedes
the export reserve. A stage cannot reset the outer clock. GREEN advances to the
next state without another approval. At most two retries are permitted for a
read-only state, and only for explicitly pinned reviewed predicates. Effectful
failures are consumed. An adapter must bound every blocking operation itself;
core deadline checks cannot preempt a stuck adapter without signals.

The core checks expiry at admission and each stage. Scope, source, CI, tools,
host, inputs, commands and outputs belong in one canonical SHA-256-pinned
manifest. A new manifest requires separate manual authorization. A checksum is
an integrity pin, not a claim of publisher signature.

## Ownership and history

The launcher, framework process image and entrypoint script have independent
path/hash pins. Launch command, observed argv and script index are separately
bound. Reverification detects changed bytes or filesystem identities. Ownership
compares OS executable path/hash to the process-image pin, independently of the
launcher. PID, PPID, start-time presence and stability, executable path/hash,
exact argv/command, cwd and three complete observations remain mandatory.
Cleanup requires cooperative exit zero, reaped handle and independent absence.
Signals default to none; the low-level signaling API requires explicit authority
and fresh complete identity verification. A missing process does not reclassify
historical cleanup. Every historical classification is copied unchanged into
receipts and the final report.

## Checkpoints and evidence

START is durable before invoking a stage. GREEN is durable only after verifying
all predicates, receipt parents and output hashes. Checkpoints form a hash chain
bound to the manifest and nonce. Resume requires an independently pinned chain
tip, the same clock identity and unexpired original budget. An in-flight START,
a final record, stale tip, changed input or changed output rejects resume.
Completed effectful stages are never replayed. An exclusive root lock prevents
concurrent controllers. Native dispatcher resume is not exposed until adapter
resource reconstruction and host boot identity are integrated.

Failure records retain fixed stage/predicate, sanitized expected/observed
categories, exception subtype and errno category. Lower-level typed predicates
are retained. Primary, additional cleanup and export failures remain separate.
No raw process output or environment values belong in these records. Evidence
uses exclusive files; the report is provisional until its complete inventory and
export seal independently verify. Failed or interrupted roots are never reused.

## Remaining integration gates

1. Migrate assembly and signing to fresh root recipes and inherited deadlines;
   retain the explicit bundle/dylib correction and its adversarial tests.
2. Migrate static verification to the signed artifact provenance chain; original
   unsigned wheel hashes must remain separate from authorized signed hashes.
3. Bind final runtime acceptance and disposable confinement/lifecycle adapters,
   including denial evidence and signal-free cooperative shutdown.
4. Integrate exact interpreter, environment, Terminal ancestry, controller
   self-ownership, source/CI authenticity, audit restrictions and tool allowlists
   in the native dispatcher. Environment/TTY markers alone are insufficient to
   claim the previously proven full Terminal-context admission.
5. Integrate resume resource reconstruction, boot identity and interrupted-root
   reconciliation. The core resume contract is tested; the native CLI remains
   new-run-only.
6. Prepare a complete pinned manifest with reviewed adapters and output recipes.
   Only then offer an execution authorization envelope and executable command.

These are implementation blockers, not requests to weaken predicates or broaden
permissions. The entrypoint's review mode returns consolidated YELLOW while any
binding is missing. Do not label that review as completed qualification.

## Authority separation

Provider access, credentials, brokers, paper orders, trade execution and live
execution remain false. Non-provider acceptance is not production qualification.
Provider pilot and full-market-day execution require separate authorization and
separate manifests. Dictionary flags alone do not enforce confinement: the
native adapter migration must preserve the existing audited sandbox and denial
evidence. Codex and Computer Use must not launch Apple Terminal. A future complete
package is launched manually once and produces one report.

## Offline validation

The source suite uses mocked inspectors and child handles, synthetic clocks and
isolated files. It exercises all nine transitions and stop paths, reviewed retry
limits, early exit, identity changes, inspection denial, interrupted stages,
expired authority, stale and altered checkpoints, cleanup uncertainty, evidence
tampering, launcher/image/script substitution and exact Terminal categories.
The existing guarded complete preparation suite blocks native subprocesses,
signals, sockets and dynamic OS inspection. No native qualification is executed
by these tests.

## Integration follow-up

The static verification function is migrated into `iios_native_static.verify`;
its `run_stage` adapter requires a durable assembly GREEN receipt and the exact
fresh execution path before invoking the verifier. Signed wheel-image identity
now follows the existing signing evidence pre/post hashes; the existing signature,
load-command, manifest and unchanged-bootstrap checks remain mandatory.

`iios_native_terminal.admit_terminal` preserves the accepted exact shell/Terminal
ancestry allowlist, bounded six-level walk, TTY, marker, host and selector checks.
Its pure audit policy distinguishes audit-policy denial from OS errno. The policy
is not installed by the current dispatcher: complete read/FD/command admission
and child restrictions remain integration work, and execution stays blocked.

Rejected resume preflight now leaves the historical root unchanged. Completed
receipts are revalidated for status, predicates, authority, parents and output
hashes. Fresh-root creation rechecks parent and child identities after mkdir.

Assembly, final-runtime acceptance and complete confinement/lifecycle native
adapters are still missing. The bootstrap acceptance cannot be relabeled as final
runtime acceptance, nor can functional lifecycle or a single correlated denial
be promoted to complete confinement qualification. There is no launch-ready
package at this checkpoint; source-controlled execution readiness remains false.
