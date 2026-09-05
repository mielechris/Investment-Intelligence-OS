# Superbatch 18 — unified Living Mob Factory

Status: source-only integration and isolated acceptance. Permanent ports 5176 and 5177 are unchanged.

## Provenance and integration map

The canonical visual source is commit `5ad6a68182f92dd4d6f8910b440f63914490c572`, served on 5176 by the committed
`LiveFactoryBrowser`, `LivingFactorySpatialFloor`, and `iios_factory_browser_preview.py`. Canonical source was imported
from Git objects, never copied from the separate checkout's dirty working tree. Generated `dist` files are not source.

| Concern | Canonical component | Unified extension |
|---|---|---|
| Shell and navigation | `LiveFactoryBrowser` | Adds an in-app Expansion Wing view while retaining floor and control views |
| Factory floor | `LivingFactorySpatialFloor` | Unchanged canonical floor remains the default view |
| Theme | V6 cinematic CSS chain | `MobExpansionWing.css` uses the same obsidian, brass, gold, emerald, amber and red language |
| Characters | `CinematicCharacterPortrait`, `livingCast`, V7.5/V7.5.2 WebP assets | Deterministic Expansion briefings reuse approved portraits |
| Existing telemetry | `/living/overview`, validation and factory-truth routes | Preserved without changing their adapters |
| Expansion truth | `FixedProjectionReader` plus sanitized `Compositor` | Fixed same-origin `/expansion-wing/snapshot`; 15-second server cache |
| Browser ownership | Canonical application root | One `ExpansionWingSnapshotProvider`; no room-level projection polling |
| Publisher | Independent 60-second LaunchAgent | No browser route, invocation or inferred health |

## Truth and authority boundary

The projection artifact may be current while underlying market evidence is stale. Reader activity does not prove
publisher activity. Publisher evidence remains `UNAVAILABLE` without an authenticated receipt. Missing fields remain
null or `NOT REPORTED`; only authenticated zero-record evidence may become `AVAILABLE_EMPTY`. Candidate display is
capped at five immutable-lineage identities. All research and professional observations remain non-actionable.

The unified route is disabled unless the future 5176 command receives `--enable-expansion-wing`. It accepts GET and
HEAD only, uses fixed operational roots, validates projection schema/hash/size/freshness server-side, and has no path,
provider, Keychain, scanner, publisher, broker, ledger, order or service-control input. The browser is same-origin and
cannot select filesystem paths or read publisher envelopes.

## Character and feed rules

MAX, Policy, Macro, Sector/Market, Historical, Professional Research, Skeptic, Risk and Portfolio narration is selected
only from bounded structured-state templates. It cannot invent news, candidates, conclusions, recommendations or
activity. Motion is ambient or state-derived, honors reduced-motion preferences and does not represent persisted work.

Feed identities are derived from browser-relevant state transitions—not projection sequence, generation timestamps or
browser poll times. The feed therefore does not manufacture events from polling or repeat timestamp churn.

## Publisher churn audit

The recent live publisher observations were authentic according to the committed source-hash contract, but repeated
publications were driven by changing sanitized factory component completion timestamps and failed radar cycle IDs/source
hashes while browser-visible state remained `AVAILABLE`, `FAILED_CLOSED`, `MARKET_CLOSED_WEEKEND`, and `STALE`. Those
updates are source changes, yet most are not browser-relevant semantic transitions. Superbatch 18 does not alter the
installed publisher. A future narrow repair should derive publication identity from normalized browser-relevant state
while retaining provenance hashes separately; it must preserve genuine cycle, failure, freshness and session changes.

## Future activation and rollback

After checkpoint review, build the unified live-read-only bundle from the exact commit, verify its static hashes, back up
the existing 5176 plist and bundle byte-for-byte, and request separate approval to add only the reviewed unified build
and `--enable-expansion-wing` argument. Rollback restores only the prior 5176 plist/bundle and never changes 5177 or the
publisher. The engineering reference to 5177 remains collapsed inside Control Room and is not normal navigation.
