# Batch 9L — Living Factory Experience + Signal Provenance

## Purpose

Batch 9L turns the Batch 9K localhost browser into a living, traceable investment-factory floor without changing the production backend, market workers, Committee/Risk authority, or capital permissions.

The governing rule is simple:

> A character, opportunity card, stage marker, or dialogue line may represent activity only when IIOS has a persisted object/event or an existing read-only backend contract that supports it.

No browser animation is allowed to imply a trade, decision, agent completion, paper order, monitor result, or learning outcome that has not actually been persisted.

## Isolated architecture

9L remains an experience-sidecar batch.

- Backend 8002: unchanged.
- 9A / 9B / 9E workers: unchanged.
- 9G / 9H / 9I / 9J LaunchAgents: unchanged.
- 9K validation sidecar files: read-only.
- Direct SQLite / ledger access from the browser preview: none.
- New backend access from the preview bridge: allow-listed HTTP GET only.
- Browser preview: localhost only on `127.0.0.1:5176`.
- Broker connection: false.
- Trade execution permission: false.
- Live execution: false.

The preview bridge may GET only:

1. `/experience/factory-intelligence/overview`
2. `/experience/factory-intelligence/case/{case_id}`
3. `/intelligence/dislocation/status`

All other backend paths are rejected by the Batch 9L allow-list.

## Living factory conveyor

The visible operating chain is:

`Market → 9E Radar → Research → 8 Agents → Committee → Risk → Paper → Monitoring → Learning`

The browser calculates the most advanced visible stage from persisted state only:

- Market: an opportunity or governed case is actually present.
- 9E Radar: the 9G promotion lineage contains the opportunity.
- Research / 8 Agents: persisted case stage and/or persisted agent completions exist.
- Committee: a persisted Committee decision is present.
- Risk: a persisted Risk authorization/decision is present.
- Paper: a persisted governed paper-execution state exists.
- Monitoring: an existing factory stage/monitor object or later persisted learning state supports it.
- Learning: a matching persisted 9J outcome memory exists.

Cards use CSS transitions only after the underlying persisted stage changes. The UI does not run synthetic timers that advance cases.

## Persistent characters

Batch 9L introduces a persistent visible cast:

- MAX — factory foreman / mascot.
- Policy Analyst.
- Macro & Rates Analyst.
- Fundamentals Analyst.
- Market Structure Analyst.
- Commodities & Supply Chain Analyst.
- Geopolitics & Weather Analyst.
- Skeptic / Red Team.
- Portfolio Context Analyst.

Character identity and desk descriptions are static UI configuration. Character **activity state and dialogue are not static**:

- ACTIVE requires a persisted completion or selected-case lineage.
- WAITING is shown when no persisted activity exists.
- MAX reports the latest persisted 9G meaningful event when one is available.
- No character makes up a recommendation, order, fill, outcome, or conversation.

Batch 9M will add personalities and story behavior, but 9L deliberately keeps dialogue factual and event-bound.

## Signal provenance

Every rendered opportunity gets one of four badges:

### `JESSE DISLOCATION`

The ticker is present in the latest persisted Jesse dislocation scan and is not represented by the current rendered 9E promotion lineage.

### `9E RADAR`

The opportunity is present in persisted 9G/9E promotion lineage and is not present in the latest persisted Jesse dislocation signal set.

### `BOTH`

The same ticker is independently present in persisted 9E promotion lineage and the latest persisted Jesse dislocation scan.

`BOTH` is an overlap observation only. It does **not** infer that Jesse caused the 9E promotion or that 9E caused the Jesse signal.

### `MANUAL / OTHER`

A governed backend case exists but is not represented by the current rendered 9E promotion lineage or latest persisted Jesse signal set.

This is intentionally conservative. Unknown provenance is labeled rather than guessed.

## Jesse governed signal source

9L keeps Jesse’s original rebound/dislocation logic visible inside the factory as a governed signal-source room.

Persisted scanner logic currently works as follows:

1. Start from day losers in the governed/supplied universe when available.
2. Score financial strength from liquidity, leverage, free cash flow, operating cash flow, profitability, ROE, revenue/earnings growth, and EPS.
3. Classify the decline as structural risk, possible temporary dislocation, or unresolved using gathered news evidence.
4. Calculate the deterministic next-day +5% heuristic:
   - base 10%;
   - +0.3 percentage point per financial-strength point above 40;
   - +5 points when the decline is at least 5%;
   - +3 additional points when the decline is at least 10%;
   - +10 points for `POSSIBLE_TEMPORARY_DISLOCATION`;
   - −20 points for `STRUCTURAL_RISK`;
   - clamp to 3%–65%.
5. `BUY` requires financial strength ≥75, estimate ≥30%, and no structural-risk classification.
6. `WATCH` requires financial strength ≥60 and no structural-risk classification.
7. Otherwise the scanner returns `NO_TRADE`.

The probability is explicitly not calibrated yet. The source remains context/governed discovery only:

- trade signal: false;
- paper-order permission: false;
- auto-trade authority: false;
- trade-execution permission: false;
- live execution: false.

## Integrated 9G / 9H / 9I / 9J rooms

The living floor embeds four visible intelligence docks:

- **9G Factory Telemetry** — persisted factory/radar/event state.
- **9H Independent Grading** — detection and miss metrics from the independent benchmark.
- **9I Shadow Experiments** — complete-session count and advisory counterfactual recommendations.
- **9J Outcome Learning** — persisted outcomes, maturity, and learning-memory state.

Missing data is rendered as WAITING or WARM-UP. The browser does not backfill missing state with illustrative values.

## Clickable lineage inspector

Clicking an opportunity opens a full provenance inspector that exposes available persisted lineage:

- signal badge and source identifiers;
- 9E source candidate and promotion time;
- agent completion count and keys;
- Committee decision and confidence;
- Risk decision and authorization id;
- governed paper execution id/state;
- backend case journey objects;
- monitoring status;
- matching 9J outcome memory;
- live-execution state.

Jesse-only signals that have not been promoted show `NOT PROMOTED` instead of inventing a case id.

## WAITING and WARM-UP semantics

9L treats absence as information:

- `WAITING` — the required persisted object/event is not currently present.
- `WARM-UP` — a learning/validation layer needs more complete sessions or no matching persisted outcome is available.
- `STALE` — a sidecar exists but has exceeded its freshness contract.
- `AVAILABLE` — the underlying persisted/read-only contract returned usable data.

Unknown state is never silently converted to READY.

## Activation

Use the dedicated 9L activation script from the live IIOS checkout:

```bash
python scripts/activate_batch9l_living_factory.py
```

The activator creates/refreshes an isolated 9L worktree, builds the browser, checks Backend 8002’s existing read-only factory contract, replaces only the browser-preview LaunchAgent, validates the 9L safety contract, verifies hashes for the protected 9G/9H/9I/9J LaunchAgents, and opens `http://127.0.0.1:5176`.

It refuses activation if the live checkout changes during the process or if protected market/learning LaunchAgents are modified.

## Acceptance contract

Batch 9L is accepted when all of the following are true:

- Browser visibly renders MAX and eight specialists.
- Opportunities use the nine-stage conveyor.
- Every opportunity has exactly one provenance badge.
- Jesse logic and latest persisted scan state are visible.
- 9G/9H/9I/9J are visible inside the 9L floor.
- Clickable cases expose persisted lineage.
- No direct ledger access exists in the preview server.
- Backend access is GET-only and allow-listed.
- Backend 8002 code is unchanged from 9K.
- 9A/9B/9E and 9G/9H/9I/9J runtime agents are not restarted or edited by the 9L activator.
- No live execution permission is introduced.
- Frontend TypeScript build and ESLint pass.
- Batch 9J regressions, inherited 9K bridge tests, and new 9L contract tests pass.

## Roadmap continuation

9L is the visual/data-lineage base for the remaining experience and continuous-improvement roadmap:

- **9M — Character & Story Engine:** consistent MAX/agent personalities, debate, adult/dark humor tied strictly to persisted events.
- **9N — Interactive Case Theater:** replay discovery through outcome using persisted lineage.
- **9O — Daily Factory Episode:** automated end-of-day story/report built from measured events, calls, misses, saves, paper performance, lessons and next focus.
- **9P — Chief Intelligence Office / Continuous Improvement Engine:** advisory-only IIOS self-improvement memos and browser room.
- **9Q — Experiment & A/B Laboratory.**
- **9R — Data Expansion Factory.**
- **9S — Agent Performance League.**
- **9T — Market Regime Intelligence.**
- **10A — Unified Production Browser.**
- **10B — Paper Performance Qualification.**
- **10C — Portfolio Intelligence.**
- **10D — Capital Preservation & Stress Lab.**
- **10E — Governed Capital Readiness.**
- **10F — Institutional Investment Firm OS.**

The permanent operating loop remains:

`Observe → Discover → Research → Debate → Decide → Risk → Paper → Measure → Grade → Learn → Identify Weaknesses → Recommend Upgrades → Shadow-Test → Human Approves → Improve → Repeat`
