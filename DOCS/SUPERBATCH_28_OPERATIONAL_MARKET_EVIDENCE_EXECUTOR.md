# Operational Market Evidence Executor

This source-only checkpoint adds a disabled-by-default, restart-safe coordinator between the immutable one-day policy and the already reviewed Financial Datasets credential and verified-TLS boundaries. It performs no Keychain or network access merely by importing, validating, or starting the existing disabled supervisor.

The full immutable plan contains 50 one-credit identities: ten opening snapshots, ten prior-session OHLCV observations, ten intraday snapshots, one MU company-facts observation, nine fund/ETF baselines, and ten closing snapshots. `PARTIAL_SESSION_LATE_START` is a separate deterministic plan. It never creates opening identities after the opening window and includes only still-available windows; its plan hash and exact maximum cost are computed from the resulting immutable rows.

Every request is durably recorded as `PLANNED`, `RESERVED`, and `DISPATCH_STARTED` before transmission. It then becomes `CONFIRMED`, `AMBIGUOUS`, or `FAILED_PRETRANSMISSION`. Confirmed and ambiguous identities can never be sent again. A process recovered with `DISPATCH_STARTED` classifies that identity ambiguous and charges it once. Only a proven pre-transmission failure remains unspent, and automatic retry is prohibited.

Raw licensed responses and receipts use separate owner-only directories. Writes use atomic replacement, file fsync, and directory fsync. Browser projection contains only lifecycle counts, credit counts, phase, next gate, plan classification, stages, and false authority fields. It contains neither provider bodies nor request identities.

Production execution remains disabled until a separately reviewed supervisor integration supplies all eight gates: immutable policy, executor, credential-presence record, TLS trust, cost contract, request plan, state store, and receipt store. The fixed provider contract is `api.financialdatasets.ai:443`, `X-API-KEY`, the dedicated Financial Datasets Keychain selector, and only `/prices/snapshot`, `/prices`, and `/company/facts`. No secret is stored, logged, hashed, projected, or passed outside the header boundary.

The first operational authorization after this checkpoint is restricted to one SPY `/prices/snapshot` canary and at most one credit. The daily plan must not be authorized until that canary creates a validated persistent receipt visible through the authenticated Museum projection.
