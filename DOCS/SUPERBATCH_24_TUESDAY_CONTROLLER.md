# Tuesday paper-observation controller commissioning

The controller package is source-controlled, uninstalled, and application-level disabled by default. Its persistent supervisor is separate from activation: a future launchd-managed process may be installed and running while evidence collection remains disabled. It owns no network listener, browser route, broker import, operational-ledger import, or automatic promotion path. Its fixed registry is MU, SPY, XLK, VNQ, TLT, GLD, UUP, IBIT, PFF, and BIL; runtime symbol overrides are prohibited.

The gate sequence is operational mode, session, human authorization, entitlement, fixed identity, observation phase, per-symbol budget, global budget, single-flight lock, selector validation, one credential retrieval, and one provider request. Failure before the credential gate performs no credential access. Timeout or ambiguous accounting receives no retry.

Monday September 7, 2026 rehearses `CLOSED_HOLIDAY`, zero provider requests, credits, Keychain access, candidates, synthetic observations, and operational mutations. The next allowed phase is `TUESDAY_PREMARKET_LOCKED`.

The Tuesday phase machine is strictly ordered from premarket lock through opening authorization and collection, human candidate review, Committee, Risk, forward observation, intraday and close marks, post-close audit, and completion. Restart recovers the exact checkpoint; invalid transitions fail closed.

The proposed LaunchAgent label is `com.iios.expansion-wing-tuesday-controller`. The reviewed template uses the fixed committed interpreter and module `expansion_wing.tuesday_controller_service`, explicit `--supervisor` mode, an owner-only state root, `RunAtLoad`, and fail-closed restart only after an unsuccessful exit. It contains no activation, provider, credential, browser, broker, ledger, or execution argument. This batch does not create or register that plist.

The state root has the fixed inventory `installation.json`, `controller-state.json`, and, only while the supervisor is running, `controller.lock`. Directories are mode 0700 and files mode 0600. Both JSON contracts have strict top-level allowlists and deterministic content hashes. Writes use same-directory replacement plus file and directory fsync. Restart preserves phase history, sequence, request identities, budgets, authority locks, and the Monday holiday result. A missing installation projects `NOT_INSTALLED`; unsafe permissions, inventory, schema, timestamps, hashes, budgets, or authority project `FAILED_CLOSED` without revealing paths or values.

The browser receives only the scalar `iios-tuesday-controller-browser-v1` projection through the existing Expansion Wing snapshot. It never reads controller files directly and has no activation or service-control route. Installation truth comes only from a validated installation manifest; source or template presence never implies installation.

Activation still requires human review, this batch's checkpoint, a separately authorized Museum rebuild, controller installation authorization, and Tuesday-morning credit authorization.
