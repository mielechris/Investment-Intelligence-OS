# Batch 9N — Interactive Case Theater

## Purpose

Batch 9N adds a read-only governed replay theater on top of the green Batch 9M Character & Story Engine. It lets an operator select a real IIOS case and walk through the persisted decision chain without rerunning, rewriting, or reinterpreting history beyond the data actually exposed by IIOS.

The governing rule is:

> Replay the decision. Do not rewrite history.

## Visible replay chain

The theater exposes ten browser-only replay stages:

1. Discovery
2. Research
3. 8 Agents
4. Skeptic
5. Committee
6. Risk
7. Paper
8. Monitoring
9. Outcome
10. Learning

A stage may show `WAITING` even when a later stage exists if the current read-only contract does not expose that earlier artifact. This is deliberate. Downstream state does not authorize the browser to invent missing research, agent dialogue, or governance objects.

## Data sources

9N uses only existing read-only 9L/9M contracts:

- `GET /living/overview`
- `GET /living/case/{case_id}`

The browser does not call Backend 8002 directly and has no direct SQLite/ledger access.

The selected case can display:

- current 9G/9E promotion lineage;
- signal provenance (`JESSE DISLOCATION`, `9E RADAR`, `BOTH`, `MANUAL / OTHER`);
- read-only backend case-journey object IDs and statuses;
- current persisted specialist-completion roster;
- exact Skeptic-completion presence when available;
- Committee disposition/confidence/summary when exposed;
- deterministic Risk decision and triggered rules when exposed;
- governed paper-execution state when exposed;
- monitoring snapshot/return/thesis flags when exposed;
- exact case event tape from the current 9G meaningful-event window;
- exact-linked 9J market outcome and decision-quality memory when mature.

## Exact 9J lineage rule

9N inherits and strengthens the 9L truthfulness rule.

A 9J outcome can attach to a replay only through:

1. exact persisted `case_id`; or
2. exact persisted source `candidate_id` matching the 9E promotion's `source_candidate_id`.

Ticker-only learning joins are prohibited. A later NVDA case cannot inherit an older NVDA outcome merely because the ticker matches.

## Replay controls

`START`, `PREV`, `PLAY REPLAY`, `PAUSE REPLAY`, `NEXT`, and direct stage selection change only React/browser cursor state.

They do not:

- rerun research;
- rerun a specialist;
- invoke Skeptic;
- rerun Committee;
- rerun Risk;
- create an authorization;
- create or submit a paper order;
- change monitoring state;
- alter a 9J outcome/learning label;
- change a promotion threshold;
- change an agent weight;
- grant capital or execution authority.

## Missing-artifact behavior

9N never creates demonstration or placeholder cases.

Examples:

- no explicit persisted research object -> Research stays `WAITING`;
- no Skeptic completion key -> Skeptic stays `WAITING`;
- no Committee object -> Committee stays `WAITING`;
- no Risk object -> Risk stays `WAITING`;
- no paper execution -> Paper stays `WAITING` and does not imply an order;
- no exact-linked 9J outcome -> Outcome/Learning stay `WARM-UP`.

Raw specialist text is not currently exposed by the read-only case contract, so the theater does not manufacture a historical debate transcript. Batch 9M remains the separate event-bound narrative-rendering layer and clearly labels its dialogue as narrative, not raw historical agent speech.

## Browser layout

9N adds:

- Governed Case Archive rail with up to 40 currently visible governed cases;
- signal-provenance badge per case;
- ten-stage replay rail;
- browser-only playback controls;
- persisted-source artifact card for the active stage;
- scalar read-only artifact summary;
- exact-case event tape for current 9G meaningful events;
- source-ID strip across the entire replay;
- permanent Replay Integrity notice.

## Safety

Batch 9N remains experience-sidecar only:

- Backend 8002 unchanged;
- 9A / 9B / 9E unchanged;
- 9G / 9H / 9I / 9J protected LaunchAgents unchanged;
- direct ledger access: none;
- backend access: read-only GET only;
- backend write permission: false;
- broker connected: false;
- trade execution permission: false;
- live execution: false.

## Activation

9N continues to use the same localhost preview URL:

`http://127.0.0.1:5176`

Activation builds in an isolated worktree, validates Backend 8002's existing read-only contract, replaces only the browser-preview LaunchAgent, verifies the living-factory safety contract, fingerprints protected 9G–9J LaunchAgents before/after, and verifies the live IIOS checkout did not change.

## Acceptance gate

9N is accepted when:

- all inherited 9M/9L/9K contracts remain green;
- frontend ESLint and production build pass;
- the full ten-stage replay exists;
- exact case/candidate 9J joins are enforced;
- ticker-only outcome joins are absent;
- replay controls are browser-state only;
- missing artifacts remain visibly WAITING/WARM-UP;
- the story and living-factory layers remain composed and unchanged in authority;
- Backend 8002 remains unchanged;
- protected 9G–9J LaunchAgents remain unchanged;
- trade execution and live execution remain false.

## Next batch

**9O — Daily Factory Episode** will turn each completed market day into an automated, governed story/report covering best calls, misses, Risk saves, paper performance, learning, and the next session's focus—again tied only to persisted IIOS state.
