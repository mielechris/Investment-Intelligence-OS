# Native Qualification v2 local macOS launcher

The local app is the active execution design. The prepared private-control repository and runner archive remain inactive future work; neither is registered or started.

The source-controlled Objective-C/AppKit launcher has no text fields, path selection, shell evaluation, credential access or network client. It invokes only the fixed `scripts/iios-native-qualify` entrypoint with profile `observation`. A preflight admission verifies the exact branch, commit, origin, complete source inventory, durable roots, selected Mac, current UID, parent app executable hash and ad-hoc bundle signature before showing the confirmation dialog.

The confirmation has only **Cancel** and **Run Qualification**. It displays repository, full commit, branch, inventory digest, Mac UUID, profile, evidence destination, explicit resume state, zero provider requests, four false trading authorities and permanent historical `cleanup=NOT_ESTABLISHED`.

The app streams stage transitions, displays final GREEN or RED and enables **Open Evidence** after completion. The existing engine owns the nonblocking single-run lock, explicit resume checkpoint, bounded stages, cleanup, sanitized evidence and fail-closed authority contracts.

Before the v2 journal is created, the launcher also verifies that `~/Library/IIOS/evidence/preflight` is an owner-only contained directory. Any admitted source, host, app, parent-process, branch, inventory or dirty-worktree failure atomically writes one sealed receipt there. If that root cannot be safely admitted or written, the app stops before native stages and displays the bounded, copyable `EVIDENCE_EXPORT_UNAVAILABLE` diagnostic without claiming a receipt.

The bundle is built under an exclusive qualification version root, moved to `~/Applications/IIOS Native Qualification.app`, signed ad-hoc with hardened-runtime flags and verified using `codesign --verify --deep --strict --all-architectures`. Ad-hoc signing is used because the build is forbidden from reading Keychain identities. No system component, service, listener or daemon is installed.
