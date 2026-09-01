# IIOS Remote Observer Agent Instructions

This repository is an isolated remote observer. Work only within this repository and on the current feature branch.

## Safety and Authority Boundaries

- Preserve the Mac Backend 8002 unchanged.
- Preserve `LIVE_EXECUTION=false`.
- Never add broker connectivity, order-entry, ledger-write access, capital authority, trading authority, or live execution capability.
- Keep all remote telemetry strictly sanitized and read-only.
- Preserve the governed paper fund and all existing safety gates.
- Never expose, print, commit, copy, or otherwise disclose secrets, tokens, passwords, credentials, or other sensitive values.

## Deployment Boundaries

- Never modify or deploy Vercel Production.
- Use Vercel Preview deployments only, and only with explicit user approval to deploy.

## Change Discipline

- Before editing, inspect the Git worktree and preserve all unrelated user changes.
- After changes, run the relevant tests, type checks, builds, and `git diff` checks for the modified area.
- Do not commit, push, deploy, merge, delete, or otherwise perform destructive or remote-changing operations without explicit user approval.

## Reporting

When finishing work, report the files changed, validation performed, and any remaining risks or limitations.
