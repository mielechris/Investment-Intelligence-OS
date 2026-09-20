# Controller provenance and runtime exception evidence

The controller publishes `CONTROLLER_LAUNCH` into the existing checkpoint chain
before executing any qualification stage. It binds a fresh nonce, UTC creation
and monotonic time, kernel-observed PID/parent/start time, interpreter hash, exact
argv digest and category, scrubbed environment projection/digest, canonical
source-root identity, source inventory, entrypoint hash, and qualification-module
file and loaded-code digests. The context binds the current BEGIN checkpoint,
source commit, boot, issuer digest and evidence destination. Re-observation must
match before admission; stale, reused or differently bound receipts fail closed.

The fixed shell entrypoint uses Python `-I -B -S`. A qualification-only source
loader compiles `.py` bytes without reading or writing bytecode caches. The
controller additionally rejects unexpected module origins, existing module
caches and source or loaded-function substitutions. A direct script entrypoint
is distinguished from source-only module loading. Ordinary module imports cannot
assert the source-only policy.

The environment digest covers an explicit projection: fixed launch fields are
classified EXPECTED/ABSENT/OTHER, and Python path override fields record presence
only. Unapproved names and values are excluded, including credential values.
It is not a digest of secret-bearing raw environment bytes.

Stage failures, cleanup failures and export failures carry bounded exception
evidence: the last 32 frame locations, total count and truncation flag, code and
path digests, line and instruction offset, exact leaf call-site digest, and fixed
operation and target categories. UNKNOWN remains explicit when classification
is unavailable. No exception message, locals, source lines or arbitrary target
path is exported. Qualification frame locations are source-relative; external
frames are identified by digests. The controller digest refers to the sanitized
launch receipt, so it can be recomputed from an exported summary.

The summary repeats the launch receipt and binds its digest to exception evidence.
The existing content-addressed export and FINAL manifest binding remain intact.
Raw checkpoint hashes are validated against private checkpoints; exported
journals remain sanitized projections. Hash chains are integrity evidence, not
cryptographic proof against a privileged actor replacing all local evidence.

Tests use the existing offline guarded preparation command:

    python3 -B scripts/iios-native-prepare.py

A passing preparation suite or rebuilt app does not establish native qualification,
provider access, confinement acceptance, production readiness or trading authority.
One separately authorized fresh application run is needed to diagnose the previous
runtime failure. Existing failure receipts must remain unchanged.

The macOS framework launcher and kernel-observed Python application image are
separate executables. Controller admission checks each exact path and hash against
the existing hash-bound vendor framework inventory; kernel argv[0] must name the
pinned image. PID, parent PID, start-time presence and source CWD remain required.
They no longer depend on the incorrect assumption that sys.executable equals the
OS process image. Each failure has its own fixed predicate. Only exact reviewed
controller predicate strings from builtin ValueError are exported; arbitrary
exception messages remain withheld.
