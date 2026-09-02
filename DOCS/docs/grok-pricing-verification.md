# Grok Pricing Verification

Normal provider access is disabled by default even with verified pricing. A controlled request requires a separate owner-armed, single-use activation state.

## Verified Official Pricing

Retrieved 2026-09-02 from xAI-owned documentation:

- [xAI API Pricing](https://docs.x.ai/developers/pricing)
- [xAI Grok 4.6](https://docs.x.ai/developers/grok-4-6)
- [xAI Cost Tracking](https://docs.x.ai/developers/cost-tracking)

For model `grok-4.6` below the 200,000 prompt-token long-context threshold, the verified prices are USD 2.00 per 1M input tokens, USD 6.00 per 1M output tokens, and USD 5.00 per 1,000 `x_search` calls, or USD 0.005 per call. xAI returns actual request cost through `usage.cost_in_usd_ticks`; one USD equals 10,000,000,000 cost ticks. The pricing page did not display an effective-date value at retrieval; this record uses the owner retrieval/review date and expires 2026-12-01.

The enforced maximum is 16,000 input tokens, 2,000 output tokens, and 3 X Search calls. In integer cost ticks:

$$
320{,}000{,}000 + 120{,}000{,}000 + 150{,}000{,}000 = 590{,}000{,}000
$$

Applying the $1.25$ safety multiplier yields 737,500,000 ticks (USD 0.07375), below the independent 800,000,000-tick (USD 0.08) reservation and actual-cost cap.

## Controlled One-Shot Procedure

An authorized owner may arm exactly one controlled request through the owner-only `arm_controlled_xai_request` interface using a separate approval token and an audit activation ID. Only a SHA-256 fingerprint of the approval token is persisted. The token itself must never be logged, committed, or stored. The state is consumed before provider dispatch, cannot be replayed, and records the reservation ID. `revoke_controlled_xai_request` revokes an armed but unused activation by its activation ID. A consumed activation cannot be reused or revoked; any actual cost above USD 0.08 creates a durable integrity block requiring explicit remediation.

The owner must maintain a non-secret provider source name and reference, review identifier, verification date, expiration date, model, currency, and integer USD-tick prices for input tokens, output tokens, and X Search calls. Review the reservation calculation and safety margin before changing pricing provenance.

Before enabling the verified policy, run the offline Grok governor tests, Python compile checks, and `git diff --check`. Do not put credentials, provider responses containing secrets, or live-execution settings in this record. `LIVE_EXECUTION=false` and all IIOS authority gates remain unchanged.