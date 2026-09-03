# IIOS Expansion Wing — Cross-Asset Dual-Book Machinery

## Boundary

This branch is paper-only and additive. It does not replace or control 9A, 9B, 9E, 9G, repaired 9H, 9I, 9J, Factory Watch, the Living Wall publisher, Preview, Committee, Risk, any broker, or any LaunchAgent. The Expansion Wing endpoint reads only an explicitly configured sanitized JSON snapshot. Missing inputs render `UNAVAILABLE`; incomplete inputs render `INCOMPLETE`; stale inputs render `STALE`.

## Machinery

- One Opportunity Passport with equity, ETF, IPO/new-listing, Treasury/bond, commodity, futures, and later-compatible currency/digital-asset classes.
- IPOs, bonds, Treasuries, futures, currencies, and digital assets start observation-only. Futures additionally require contract size, margin, leverage, expiry, rollover, and overnight-risk evidence.
- Separate Tactical ($3,000 maximum) and Strategic ($5,000 maximum) paper books plus an untouched $2,000 cash/Treasury reserve. Allocations are ceilings, never deployment requirements.
- Tactical sizing, daily-loss, concurrent-exposure, cost/partial-fill, and end-of-day classification contracts.
- Strategic sizing, concentration/correlation, thesis, invalidation, and longer-horizon contracts.
- A ten-dimension Market Regime Director that becomes transitional when evidence is missing or stale.
- A paper allocator that uses probability-weighted return/loss, drawdown, time, liquidity, correlation, evidence, complexity, and cash opportunity cost.
- Consent/right-to-use interview packets, human transcript approval, governed principles, point-in-time walk-forward tests, three isolated strictness policies, and fail-closed resource budgets.
- Opening, closing, and daily reports derived only from the sanitized projection.

## Living Wall contract

`GET /expansion-wing/status` exposes the existing UI with explicit truth states and fourteen rooms. It has no mutation route. Its response strips credential, secret, token, password, API-key, and raw-log keys and caps collection, string, and nesting depth at the projection boundary. When no snapshot is configured, every operational section is visibly unavailable; the UI never invents characters, trades, returns, or evidence.

## Activation

There is no activation script. No service, scheduler, publisher, credential, or Vercel configuration is installed or modified by this branch. The frontend defaults to its visibly labeled synthetic fixture. The Backend 8002 URL is unreachable unless both `VITE_EXPANSION_WING_LIVE_READONLY=1` and `VITE_BACKEND_RECOVERY_GREEN=1` are deliberately supplied at build time. Backend artifact development may point `IIOS_EXPANSION_WING_SANITIZED_SNAPSHOT` at a copied JSON fixture. Operational activation requires a separate final review and explicit owner authorization.
