# Security policy

This private repository controls code execution on one selected Mac. Only reviewed changes on protected `main` may alter the workflow, bindings or verifier. Pull requests and tags never trigger qualification. Repository administrators must preserve required environment approval, read-only workflow permissions and exact runner-group access.

Never commit registration tokens, removal tokens, credentials, runner `.credentials*` files, `_diag` logs, machine identifiers, native result files or unsanitized evidence. Report suspected runner compromise by stopping the runner, revoking its GitHub registration, preserving owner-only diagnostics and keeping historical qualification results unchanged.
