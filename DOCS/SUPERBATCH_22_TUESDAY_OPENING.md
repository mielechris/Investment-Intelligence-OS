# Tuesday Opening-Day Runbook

## Preconditions

- Exact reviewed commit, clean worktree/index, synchronized feature branch.
- Protected services healthy and unchanged.
- Projection integrity valid; publication freshness and underlying evidence freshness reported separately.
- Operational paper is $10,000 NAV/$10,000 cash with zero activity.
- All authority locks false.
- Approved calendar identifies the phase.

## Phase gates

`PRE_MARKET` inventories evidence without creating identities. `REGULAR_SESSION` permits research evaluation only for complete, current, licensed evidence with immutable lineage. `POST_MARKET` freezes new opening actions and awaits outcomes. `POST_CLOSE` reconciles evidence, costs, decisions, and null outcomes. Any unsafe input becomes `FAILED_CLOSED`.

For each of the 24 products record tested, evidence available, contract complete, research eligible, paper eligible, candidate count, blocker, and outcome availability. Unsupported desks remain explicitly `NOT_ACTIVATED`, `UNAVAILABLE`, `INCOMPLETE`, `STALE`, `FAILED_CLOSED`, or `RESEARCH_ONLY_UNPRICEABLE`.

For each of the 16 methods record product eligibility, required session/freshness/liquidity, costs, sizing hypothesis, invalidation, exit, holding period, benchmark, minimum sample, drawdown, calibration, ranking eligibility, and failure behavior. Missing results remain null and `INSUFFICIENT_SAMPLE`.

No fixture is live evidence. No product registry entry implies operational availability. No method ranking, candidate, recommendation, paper order, ledger write, broker connection, or execution is authorized.
