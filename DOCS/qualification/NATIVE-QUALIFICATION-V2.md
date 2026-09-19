# IIOS Native Qualification v2

Status: source/offline implementation. Runner registration and selected-Mac execution are separate activation gates. Offline tests do not establish native GREEN.

## Stable command and durable roots

`./scripts/iios-native-qualify --profile observation` is the single qualification entrypoint, restricted to a manually dispatched enrolled self-hosted selected-Mac job. There is no Terminal ancestry requirement, expiring package, copied launch hash or temporary qualification root.

- `~/Library/Application Support/IIOS/runtime`: verified offline wheelhouse and project venv, keyed by vendor/lock identity. The vendor framework stays at `/Library/Frameworks/Python.framework/Versions/3.14`.
- `~/Library/Application Support/IIOS/qualification`: runner and workspace, host enrollment, permanent `native-v2` journal, working data/checkpoints and scratch files.
- `~/Library/Application Support/IIOS/evidence`: exclusive content-addressed exports. Files are 0400 and sealed export directories 0500; outer/work directories are 0700. Hashes and seals detect mutation; they are not WORM protection against an administrator.

The existing 40-package version lock is unchanged. The additional artifact lock pins exact wheels, sizes and hashes. The installer uses only the local wheelhouse, with no index, dependency resolution, source builds, user pip configuration or cache. Wheel RECORDs, installed RECORDs, complete venv membership, module origins and native dependencies are verified. Vendor ensurepip supplies installation tooling; it is separate from the project lock. Provider packages are not imported for qualification. No global pip install, framework relocation or system installation is performed.

`--check` performs static preparation only. `--stage-artifacts <durable-qualification-directory>` verifies and copies already-acquired exact wheels; it never downloads. Neither mode issues native evidence. Missing artifacts or vendor Python fails closed.

## State and resume

Version 2 JSON checkpoints are append-only, hash-chained and fsynced under an exclusive lock. `state.json` is an atomic convenience projection; the journal remains authoritative. Failures and source revisions are never overwritten. There is no retry loop.

An existing invocation requires explicit `--resume`, exposed as the workflow Resume input. A committed source fix can resume without regenerating a launcher. All native prerequisites are revalidated on every explicit invocation; old approvals are never reused as fresh approvals across source/boot changes. A verified venv can be reused after full revalidation. `--rebuild-runtime` preserves a partial/drifted environment under a retired name before one deliberate rebuild; nothing is deleted.

Launch intent is journaled before spawning, followed by PID and three independent identity observations before ACK. Each child has a separate 180-second self-alarm. Normal cleanup is cooperative and requires wait/reap plus three absence observations. Signals are restricted to held direct-child handles after current identity checks. Recovered PIDs are never signaled. Same-boot unresolved launch intent without a PID blocks resume. Known same-boot PIDs must be independently absent. Prior-boot PIDs are never inspected because they may have been reused.

Historical `cleanup=NOT_ESTABLISHED` is permanent. Configuration pins the independently verified reboot review. A different current boot establishes only that prior-boot processes cannot survive, recorded as an exception without rewriting historical cleanup. Legacy code, packages, receipts and missing-input findings remain unchanged.

## Native stages and claim

1. Verify clean exact source and artifact/version lock correspondence.
2. Verify PSF signatures and exact vendor Python version; build/reverify the project venv at its final location.
3. Bind current boot and preserve prior-boot exceptions.
4. Test the existing macOS ownership inspector with an owned READY/ACK child: PID, PPID, start, executable/hash, argv, cwd and stability.
5. Perform allowed/denied dummy filesystem, credential-boundary, loopback-network and subprocess comparisons. Require correlated kernel sandbox denials and stable process identity. EPERM alone is insufficient; actual credential stores are never read.
6. Launch sandboxed scheduler, publisher and backend roles. Verify READY/ACK nonce/config/authority and independent listener ownership.
7. Verify GET and HEAD over loopback TLS with a local synthetic certificate, without installing system trust.
8. Exercise existing Truth Spine seed and canonical lineage contracts across three real role processes. Scheduler publishes three synthetic seeds, publisher validates and links them, and backend returns the exact projection. Seeds remain zero executed provider requests. This tests core synthetic lifecycle, not the full-day production service or 475-request milestone.
9. Verify cleanup, process/listener absence and unchanged runtime/vendor identity.
10. Export and verify the sealed journal/summary, then record final GREEN/RED. Hosted preparation produces only preparation results.

All four trading authorities remain false: `broker_connection`, `paper_order_permission`, `trade_execution`, `live_execution`. Provider calls/credentials, account APIs, brokers, orders, production ledgers and system installation are outside the command.

## One-time runner activation (not executed by this source batch)

Registration requires GitHub account access and a short-lived token, outside qualification. Never store that token in source or evidence.

An administrator must first protect environment `iios-native-qualification` with required approval and a trusted-branch allowlist, and set repository variable `IIOS_NATIVE_TRUSTED_REF` to the fully qualified reviewed branch. Restrict runner access to this workflow using runner-group policy where supported. This repository is public: labels and job environment variables alone do not stop another workflow from targeting the runner. If workflow restrictions cannot be enforced, use an isolated runner-control repository/dedicated Mac account before activation. No PR workflow may target this Mac.

In GitHub **Settings → Actions → Runners → New self-hosted runner**, choose macOS ARM64. Verify the download against GitHub's displayed SHA-256. Install under `qualification/runner`, configure `qualification/runner-work` as the work directory (including runner internal temporary files), and add label `iios-selected-mac`. Use the selected user's session or user LaunchAgent; v2 does not install a system LaunchDaemon or invoke sudo.

Create owner-only `qualification/selected-host.json` (0600) with administrator-verified values:

```json
{"repository":"mielechris/Investment-Intelligence-OS","runner_name":"ENROLLED_RUNNER","trusted_ref":"refs/heads/REVIEWED_BRANCH","hardware_uuid":"SELECTED_MAC_IOPLATFORMUUID","uid":501}
```

Read the actual UID/hardware UUID on the selected Mac; do not assume the example UID. The command checks these against the machine, repository, workflow ref, runner name and exact commit. Enrollment is a trusted host-administrator control, not cryptographic GitHub job attestation. It is never synthesized from job variables.

Stage retained wheels once, confirm the vendor runtime already exists, then manually dispatch **IIOS Native Qualification v2**. Review RED and cleanup before choosing Resume after a source fix. No automatic job retry is configured.

## Migration and risks

Retire old conductor packages operationally; do not delete or reinterpret them. V2 does not use the privately reconstructed framework or 556-image reference as its runtime; vendor/venv qualification is a new scope. The legacy bootstrap and reconciliation validators stay unchanged.

Removed risks: temporary-root loss, framework relocation/signing churn, Terminal ancestry gates, copied approval hashes and package regeneration. Remaining risks: native sandbox/log availability, inspector permissions, vendor updates, admin-writable installed files, package/native compatibility, same-account evidence mutation, interrupted process registration and runner exposure. Pre/post hashes do not defeat malicious transient modification by an administrator. Native GREEN is neither OS boot attestation nor production readiness.

References: [GitHub runner setup and public-repository warning](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners), [GitHub environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments), [Python venv](https://docs.python.org/3/library/venv.html).

## Source/offline validation status

The v2 suite passes 38 tests with socket, process launch and signal effects denied, including pure seeded-role lineage and tamper rejection. All 40 retained wheels pass exact hash/size, RECORD and archive checks. YAML parsing, shell syntax and Python AST checks pass.

The legacy 1,057-test guarded selection run under durable Application Support roots is RED: 902 passed, 7 failed and 148 errored. A focused reproduction confirms `truth_spine_observation_roles.admit_roles` rejects `Application Support` with `DISPOSABLE_PATH`. Other failed cases have not all been individually diagnosed. This legacy admission policy is deliberately unchanged; v2 does not claim legacy-suite compatibility or all-suite GREEN. No tests were moved back to temporary roots to manufacture a pass.

Runner registration, exact-commit GitHub CI, vendor/venv build execution, OS confinement, ownership and native acceptance remain pending. The new manually dispatched workflow is source-only until repository/runner controls are configured and publication is separately authorized.
