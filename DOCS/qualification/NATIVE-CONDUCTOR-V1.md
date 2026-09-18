# IIOS Native Qualification Conductor v1

Source integration and substituted-effects tests do not establish native qualification.
The manual entrypoint never grants provider or production authority. Every external
input, profile review, host identity and source/CI receipt must be pinned before a
launch package can be admitted. Missing inputs fail closed; there is no legacy
command fallback or incomplete-adapter success route.

## State and adapter map

| Order | State | Implementation |
| --- | --- | --- |
| 1 | SOURCE_AND_CI_ADMISSION | admission.admit_source; exact inventory and CI parents |
| 2 | HOST_AND_TERMINAL_ADMISSION | terminal.admit_terminal; TTY, ancestry, host and self-ownership |
| 3 | HISTORICAL_PROCESS_RECONCILIATION | dispatcher; PID 35731 only, three absent observations |
| 4 | FRESH_OUTPUT_ROOT_QUALIFICATION | dispatcher; exclusive 0700 root and inode binding |
| 5 | PRIVATE_RUNTIME_ASSEMBLY | assembly.run_stage; existing corrected assembly and bottom-up sealer |
| 6 | STATIC_SIGNATURE_AND_INVENTORY | static.run_stage; complete final-location verifier |
| 7 | STATIC_RUNTIME_REFERENCE | image_policy.run_stage; independent external production reference |
| 8 | FINAL_RUNTIME_ACCEPTANCE | runtime_adapter.run_stage; owned final-runtime diagnostic |
| 9 | DISPOSABLE_CONFINEMENT_AND_LIFECYCLE | lifecycle.run_stage; existing Truth Spine role runner and controlled denial collector |
| 10 | EVIDENCE_EXPORT_AND_VERIFICATION | evidence exporter; complete inventory and independent verification |

Names in the implementation column have the `iios_native_` prefix except the reused
Truth Spine and denial collectors. Each adapter requires exact GREEN predecessor
receipts and the audit installation parent. Runtime acceptance cannot accept static
verification or a bootstrap image receipt in place of production evidence.

## Audit and ownership

The entrypoint installs its preparation no-effects hook before repository imports,
verifies source bytes, then installs NativeAudit before dispatcher import or handler
resolution. The audit has explicit stage operations, exact read inputs and fresh-root
writes, tracked file descriptors, one-use command grants, read-only inspection symbol
scopes and fixed sanitized denials. Lazy source compilation rechecks hashes. Unknown
bytecode, credential paths, network effects and signals are rejected. After static
verification the controller cannot write the sealed runtime. This Python guard is
not an OS sandbox attestation; sandbox enforcement requires native evidence.

The launcher, actual process image and script have separate path/hash bindings.
PID, PPID, process start time, executable hash/path, exact argv/command, cwd and
stability remain mandatory for all three observations. Cooperative exit zero,
reaping and independent absence are required. The conductor sends zero signals. V3 role inspection uses a bounded signal-free
transport around the existing inspector and listener parser; timed-out handles
remain unresolved instead of being killed.
Constructor uncertainty and partial cleanup cannot become GREEN. Historical
cleanup classifications, especially attempt 10 UNVERIFIED, are immutable.

## Disposable lifecycle

The adapter reuses admit_roles/configuration, ObservationLifecycle, startup receipts,
ACK/TLS/health, cooperative stop, listener reconciliation and Children ownership.
The v3 descriptor adds conductor, source, host, output identity, production reference
and acceptance parents. It binds the framework process image independently of the
launcher and uses the original Darwin monotonic clock domain without resetting it.

The same exact profile covers the role runner and dummy denial trials. The shared
profile admission rejects broadened rules even when a changed profile is rehashed.
Only a separately pinned review can bind the template and exact inspection tools.
The profile revision adds exact ps/lsof and process-image paths; it must
not be described as previously native-qualified. Filesystem, dummy credential-marker,
dummy executable and fixed loopback comparisons require both an allowed baseline and
OS-attributed denial from the existing bounded collector. Errno alone never qualifies.
No actual credential, provider, gateway, broker or protected ledger is accessed.

## Deadlines, failure and resume

One original monotonic start covers preparation and all stages. Stage caps use the
remaining work boundary; cleanup and export have independent reserves and cannot
borrow or reset time. GREEN automatically advances. Effectful failures are consumed;
only explicitly reviewed read-only predicates can retry within their original cap.
Primary, secondary and cleanup failures retain lower-level stage/predicate, sanitized
expected/observed category, exception subtype and errno category.

START is durable before an effect. GREEN checkpoints bind the manifest, nonce,
previous receipt, output hashes and audit parent. Native resume requires an externally
pinned chain tip, original budget and boot-session identity; it repeats source/CI,
Terminal and registered-PID admission. Interrupted or failed effectful stages cannot
resume. A failed assembly requires a fresh root and renewed bundle. No failed artifact
is overwritten or reused.

## Offline validation and authority

The complete pipeline regression invokes actual stage adapters, policy construction,
receipt checks, checkpointing and export verification with native external effects
substituted. It covers every stage failure and verifies final native-shaped evidence.
Separate regressions cover ownership, PID reuse/denial, scope substitution, deadlines,
resume corruption, audit order/bypasses, profile mutation, partial cleanup, tampering
and report overflow. Assembly preparation, OS signatures and role processes remain
native facts; mocked effects are never exported as qualification evidence.

Provider, credential, broker, paper-order, trading and live-execution authorities
remain false. production_qualified remains false. Provider pilot and full-market-day
execution require separate authorization. Codex does not launch the manual command.

## Bootstrap and production image scopes

`BOOTSTRAP_IMAGE_REFERENCE_V1` wraps the unchanged accepted bootstrap payload and
its exact 557-image contract. Its interpreter and original payload hash remain
independently pinned. It cannot satisfy a production-runtime receipt.

`PRODUCTION_RUNTIME_IMAGE_POLICY_V1` is compiled by `STATIC_RUNTIME_REFERENCE`,
between static signature/inventory verification and final-runtime acceptance.
Inputs are the external completed manifest, static Mach-O UUID/dependency
reports, the approved production import plan, signed shared-cache catalogue and
separately reviewed Apple-signed standalone images. Inputs are hash-bound. The
policy is external to the runtime, published exclusively, reconstructed and bound
to the preceding static GREEN receipt. No dynamic observation can extend it.

All private dependencies must close within the seal or the admitted OS universe.
Tk-related files, imports, dependencies and observed images are forbidden.
Required private images and direct OS dependencies form the minimum count;
independently approved optional OS candidates form the remaining allowed universe.
Its total cardinality determines the upper count and complete report bound. This
is an allowed-universe policy, not a claim that all optional OS images must load.
Both dynamic scans must be complete, contain required images, match the exact
policy identities, contain no duplicate paths, and match in order and content.
The accepted image-address stability check also remains in the generated child.
Mapped-memory integrity remains UNVERIFIED; boot attestation remains UNRESOLVED.

## Minimal inspector profile revision

Only ps and lsof are additional executable grants. The parent receives the exact
sandbox once; v3 role children execute the pinned interpreter directly and inherit
that sandbox. Application admission accepts only five fixed inspector/listener
command templates, the exact safe environment, a one-second cap and 65,536 bytes
per stream. Every PID must be self or retained from an actual owning handle.
Listener queries intersect the fixed port with one registered PID; broad lsof
listing is rejected. PID reuse remains subject to full independent owner identity
comparisons. Missing hashes, extra tools, shell options and altered argv fail.

Profile template and rendered bytes, source review, OS build/identity, host, tool
hashes and command policy are bound together. The controller verifies each tool's
Apple anchor before lifecycle effects; no source test claims that native check ran.
Old profiles are preserved and cannot satisfy the new scope. Sandbox-attributed
denial still requires the existing OS collector; an audit denial or EACCES alone
never substitutes for OS confinement evidence.

## Canonical preparation inputs

Input pinning opens every ancestor through retained no-follow directory handles,
checks owner/mode/device/inode before and after reading, and verifies file bytes
and stable file metadata. Preparation and native admission share this function.
Symlink ancestors, traversal and same-byte directory replacement fail closed.
The audit policy still rejects all symlinks; no alias grant is introduced.

The SDK header is a preparation provenance input, not a native adapter pathname.
Package preparation must bind its reviewed versioned SDK path directly rather
than the mutable MacOSX.sdk selector. Existing historical records remain intact;
this is a fresh inventory binding, not a rewrite of old evidence.

The legacy entrypoint failure before fresh_root() printed sanitized RED diagnostics but
has no native journal/export receipt. Do not fabricate those records or interpret
native_execution_entered as evidence of a launched workload. A reconstruction
must distinguish reported stdout, independently verified inputs/current absence,
and source-order inference from a persisted native observation.

## Source-only lazy imports

The audit installation receipt binds REVIEWED_SOURCE_ONLY_V1 and all exact module
origin/source hashes. Before dispatcher loading, a closed import finder admits
only built-in/frozen modules, exact pinned source origins, and exact pinned native
extensions. Source loaders compile stable no-follow admitted bytes directly with
a 16 MiB bound. They never probe or write .pyc caches; sourceless bytecode and
custom loaders fail closed. The audit retains its blanket bytecode rejection.
The meta-path installation and dont_write_bytecode setting are reverified at
stage/command boundaries. No first observation establishes source trust.

A rejected cache lookup retains a bounded reviewed source origin, its parent
hash and expected cache pathname; unknown paths are redacted. The existing final
checkpoint/export chain retains those diagnostics. Cleanup callback facts are
now retained in the report, including absent workload children and unresolved
constructor uncertainty. Hash-verified local export is not a new OS or signature
attestation. If storage/export itself fails, the result remains failed and must
not be described as an authenticated export.

After admitted authorization and audit installation, early failures now receive
a bound report/inventory/export in an exclusively created unused root. An existing
root is never reused or overwritten, and no stage receipt or cleanup verification
is invented. Authorization/preparation failures before that boundary stay read-only.
Export/storage failures retain both the original and export failure in terminal
output and never claim successful persistence.
