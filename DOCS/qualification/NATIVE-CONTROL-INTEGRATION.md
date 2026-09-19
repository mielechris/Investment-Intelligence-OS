# Native Qualification v2 private control integration

Status: inactive future work, preserved for review. The private repository does not exist, the runner is not installed or registered, no token was requested, and native qualification was not executed. The reviewed local macOS launcher is the active execution design.

## Trust boundaries

`IIOS-Native-Control` is the sole repository allowed to schedule the selected Mac. Its workflow has only `workflow_dispatch`, runs a GitHub-hosted admission job first, and rejects any context other than the exact repository, protected `refs/heads/main`, branch ref type, empty pull-request refs and `native=true`. The selected-Mac job names environment `iios-native-qualification`; GitHub must hold it until a required reviewer approves the deployment.

The selected-Mac job checks out the private control repository first and verifies every control file against `CONTROL-FILES.json`. It then checks out the exact bound `mielechris/Investment-Intelligence-OS` commit in detached state with credentials persistence, submodules and LFS disabled. The standalone control-side verifier checks the repository URL, commit, clean/untracked status, Git index modes, every tracked path, byte length, mode, SHA-256, ordered inventory and inventory digest before any IIOS Python or shell file executes. V2 independently repeats the repository, commit and inventory digest verification before host admission.

The source checkout remains read-only by contract during qualification: its full inventory is checked before and after each native stage. Runtime, checkpoints and evidence are written only below the separately bound `~/Library/IIOS` root.

## Control repository inventory

The generated candidate contains exactly:

- `.github/workflows/native-qualification.yml`
- `.gitignore`
- `CONTROL-FILES.json`
- `README.md`
- `SECURITY.md`
- `config/selected-host.schema.json`
- `config/source-binding.json`
- `scripts/collect_evidence.py`
- `scripts/seal_source.py`
- `scripts/verify_source.py`

`config/source-binding.json` contains the exact repository, full commit, complete ordered source inventory, inventory SHA-256 and false authority map. `CONTROL-FILES.json` seals every other control-repository file. The candidate is built only from a clean local IIOS commit into an exclusive directory under `~/Library/IIOS/qualification`.

## Evidence boundary

Internal owner-only checkpoints may contain process inspection details needed for reconciliation. Exported evidence is a separate projection: home paths become `$USER_HOME`; runner name, hardware UUID and GitHub run identifiers are omitted; credential-shaped strings fail export. The control collector accepts one content-addressed v2 export, verifies its manifest and file hashes, rechecks the false-authority and zero-provider-request claims, scans for machine paths, tokens, private keys and machine identifiers, and copies only `manifest.json`, `summary.json`, `journal.json` and a new artifact hash manifest.

## GitHub configuration

The repository must be private. Protect `main` against force push and deletion and require reviewed pull requests. Configure environment `iios-native-qualification` with a required reviewer, deployment branch `main`, no secrets and self-review prevention where a second administrator exists. Set Actions workflow permissions read-only. If runner groups are available, expose the `iios-native-control` group only to this repository. No public repository, fork or pull-request workflow may target the selected runner.

GitHub currently makes required-reviewer protection unavailable to private repositories on GitHub Free, Pro and Team. The integration therefore stops before runner registration unless the repository plan exposes **Required reviewers** for this private environment. Merely creating the environment does not satisfy the manual-approval contract.

The exact runner labels are `self-hosted`, `macOS`, `ARM64`, `iios-selected-mac`. The enrolled host file is 0600 and conforms to `config/selected-host.schema.json`; it pins the private repository name/ID, owner ID, protected ref, workflow, public source repository/commit/inventory, runner name, hardware UUID and UID. Hardware and runner identity are verified locally but omitted from exported evidence.

Installation and removal procedures live in the generated control repository README. Historical `cleanup=NOT_ESTABLISHED` is permanent. Provider requests remain zero and broker connection, paper-order permission, trade execution and live execution remain false.
