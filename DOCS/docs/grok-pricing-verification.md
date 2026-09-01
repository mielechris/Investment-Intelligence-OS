# Grok Pricing Verification

Provider access is disabled by default: `pricing_verified` must remain `false` until an authorized owner verifies current xAI model and X Search pricing.

The owner must record a non-secret provider source name and reference, review identifier, verification date, expiration date, model, currency, and integer USD-tick prices for input tokens, output tokens, and X Search calls. Review the reservation calculation and safety margin, update the server-side policy in a reviewed change, and set `pricing_verified` to `true` only in that same reviewed change.

Before enabling the verified policy, run the offline Grok governor tests, Python compile checks, and `git diff --check`. Do not put credentials, provider responses containing secrets, or live-execution settings in this record. `LIVE_EXECUTION=false` and all IIOS authority gates remain unchanged.