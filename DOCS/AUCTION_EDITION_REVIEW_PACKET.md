# IIOS Living Wall — Auction Edition review packet

Status: local implementation and room-dialog accessibility repair complete; physical 4K display acceptance pending.

## Architecture

- `auctionRegistry.ts` is the canonical 18-room, character, provenance, and exact event-route registry.
- `auctionSceneModel.ts` is the pure evidence-to-scene boundary. It accepts only complete event receipts, quarantines unknown event types, separates historical replay, preserves `UNKNOWN`, and freezes movement unless truth is safe and `AVAILABLE/CURRENT`.
- `AuctionFactory.tsx` renders the 16:9 architectural cutaway and close-room views.
- `LivingWallApp.tsx` connects Wall Art Mode, Story, Replay, Command, Expansion Wing, Factory Watch, Case Theater, and the collector plaque.
- `AuctionEdition.css` supplies the responsive 4K composition, restrained animation, lighting states, pause behavior, reduced-motion behavior, print/still-frame mode, and OLED drift.

## Event-to-animation mapping

Only the exact keys in `EVENT_ROOM` may illuminate a room. A receipt must also contain a valid timestamp and a case or entity lineage identifier. Unknown or incomplete events do not animate. Stale, unavailable, conflicting, or unsafe truth freezes all non-policy-locked rooms.

The governed route is Radar → Research → External Intelligence → Committee → Skeptic → Risk → Paper Execution → Portfolio → Monitoring → Learning. Policy, Macro, Judgment, Evidence, Thesis, Control, Replay, and Expansion are independently selectable architectural rooms with explicit source mappings.

## Safety posture

- Preview observer contract only.
- `telemetry_read_only=true` is required before presentation is considered safe.
- Direct ledger, backend-write, trade, and live-execution authority remain false.
- Paper Execution and Expansion remain visually locked.
- No case, dialogue, performance, or movement is created without a supporting field or receipt.
- Remote aggregate truth intentionally produces “The House Is Quiet” when detailed receipts are not exposed.

## Validation captured

- Auction normalization: 9/9 passing.
- Room-dialog keyboard accessibility: 7/7 passing.
- Deterministic desktop, ultrawide, 3840×2160 CSS-target, 16:9 still-frame, art, fullscreen, reduced-motion, and dialog-semantic checks: 5/5 passing.
- Living Wall API safety and projection: 9/9 passing.
- Preview publisher and payload sanitation: 32/32 passing.
- Targeted Auction Edition ESLint: passing.
- TypeScript plus Vite production build: passing.
- Bundle: 260.75 kB JavaScript (80.88 kB gzip), 55.89 kB CSS (13.35 kB gzip).
- Asset scan: 22 established raster assets; none above 2 MB.
- Asset rights: see `AUCTION_EDITION_ASSET_PROVENANCE.md`.
- Secret-marker scan: no matches in changed Auction Edition files.
- `git diff --check`: passing.

## Visual and performance acceptance

Safari WebDriver held its CSS viewport at 1512×874 during the clean-browser review. Its 2× native captures are honestly retained as 3024×1748 near-3K artifacts and are not upscaled or represented as 4K. Deterministic tests cover the intended desktop, ultrawide, and 3840×2160 CSS layout targets without adding browser dependencies. True physical 4K display validation remains pending on appropriate hardware. Safari console-log access and viewport emulation are also tooling limitations of that review run.

The clean-browser review found room-dialog focus containment and restoration defects. The repaired dialog now receives initial focus, declares title and description relationships, traps forward and reverse Tab navigation, closes on Escape or its close button, makes background siblings inert, and restores focus to the exact opening room control. Focused automated coverage protects those behaviors.

## Truthful UNKNOWN fields

The deployed `living_wall_truth.v1` projection supplies aggregate case/event/desk counts and paper-fund totals, but does not expose private case detail, event receipts, dialogue, or historical sessions. Those views therefore render `UNKNOWN`, “No case detail supplied,” “No replay session available,” or “The House Is Quiet” until a governed read model supplies the corresponding fields.

## Proposed commit scope

- Replace the Living Wall shell with the Auction Edition experience.
- Add the canonical registry and normalization layer.
- Add the architectural factory and visual system.
- Add focused normalization/safety tests.
- Add asset provenance and this review packet.

Production, main, credentials, LaunchAgents, authority settings, and the pre-existing `.gitignore` modification are outside the proposed commit.
