# Grok Pricing Verification

Provider access is disabled by default: `pricing_verified` must remain `false` until an authorized owner verifies current xAI model and X Search pricing.

## Partial Official Pricing Evidence

Retrieved 2026-09-01 from xAI-owned documentation only:

- Model: `grok-4.6`.
- [xAI Models and Pricing](https://docs.x.ai/docs/models): for `grok-4.6` requests below 200,000 prompt tokens, input is USD 2.00 per 1M tokens and output is USD 6.00 per 1M tokens. The configured 16,000-token input limit is below that threshold.
- [xAI X Search](https://docs.x.ai/docs/tools/x-search): confirms the `x_search` tool and its `grok-4.6` usage, but does not publish a per-call or maximum X Search tool charge.

The X Search/tool-call price is unresolved. The current server-side tool-price literal is not verified provenance and must not be treated as such. Consequently, `pricing_verified` remains `false`; no provider request, including a controlled test request, is authorized.

The owner must record a non-secret provider source name and reference, review identifier, verification date, expiration date, model, currency, and integer USD-tick prices for input tokens, output tokens, and X Search calls. Review the reservation calculation and safety margin, update the server-side policy in a reviewed change, and set `pricing_verified` to `true` only in that same reviewed change.

Before enabling the verified policy, run the offline Grok governor tests, Python compile checks, and `git diff --check`. Do not put credentials, provider responses containing secrets, or live-execution settings in this record. `LIVE_EXECUTION=false` and all IIOS authority gates remain unchanged.