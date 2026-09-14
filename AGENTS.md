# Grok Governance Repair Worktree Instructions

- Work only in this repository and on the current `feature/grok-governance-repair` branch.
- Preserve Backend 8002 and all running IIOS services unchanged.
- Preserve `LIVE_EXECUTION=false`, paper-only operation, and all existing capital, broker, order-entry, ledger-write, Committee, Risk, and trading-authority gates.
- Treat Grok/X research as advisory and untrusted. It cannot qualify evidence, promote opportunities, override Committee or Risk, allocate capital, or place paper or live orders.
- Route every xAI/Grok call through cost admission, usage accounting, citation filtering, prompt-injection screening, and quarantine rules.
- Never expose, print, commit, or copy API keys, tokens, passwords, prompts containing secrets, or credentials.
- Do not contact external providers during tests without explicit user approval.
- Preserve unrelated user changes.
- After edits, run relevant isolated tests, AST/compile validation, and `git diff` checks.
- Do not commit, push, deploy, merge, delete, start, stop, or restart services without explicit approval.
- Never modify or deploy Vercel Production.
- Report files changed, validation performed, and remaining risks.
