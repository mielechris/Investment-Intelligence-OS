# Batch 9N — Interactive Case Theater

## Purpose

Batch 9N makes governed IIOS cases replayable in the browser from discovery through eventual learning without rerunning the factory or rewriting history.

The theater is a **read-only historical inspector**. Its play/pause/next controls move only a browser cursor across already-persisted stages. They do not invoke agents, Committee, Risk, paper execution, monitoring or learning.

## Replay chain

The visible case replay is:

`Discovery → Research → 8 Agents → Skeptic → Committee → Risk → Paper → Monitoring → Outcome → Learning`

Each room shows:

- current persisted status;
- source contract;
- source object/case/candidate id;
- timestamp when exposed;
- human-readable summary of the persisted artifact;
- small scalar artifact summary when safely exposed;
- WAITING or WARM-UP when the source does not exist yet.

## Source contracts

9N uses only the Batch 9L same-origin read-only bridge:

1. `/living/overview`
2. `/living/case/{case_id}`

It does not contact Backend 8002 directly from React and does not access SQLite or the IIOS ledger directly.

The case library is built from actual governed cases plus current persisted 9G promotion lineage. Jesse overlap is used only to retain the 9L provenance badge contract.

## Stage truth rules

### Discovery

Preferred source is persisted 9G / 9E promotion lineage including source candidate id, promotion time and scores. If a governed case exists but its promotion has rolled outside the current 9G telemetry window, the theater says so explicitly and does not guess a source candidate.

### Research

The replay uses the persisted `KIMI_RESEARCH` journey object when exposed by the case-detail contract. The current read-only contract exposes object identity/state but not necessarily the research prose, so 9N does not manufacture missing text.

### 8 Agents

9G promotion lineage exposes persisted specialist completion count and agent keys.

**RAW AGENT TEXT NOT EXPOSED BY READ-ONLY CONTRACT.**

9N therefore renders the completion roster only. It never substitutes Character Story Engine dialogue as if it were literal historical agent output.

### Skeptic

A Skeptic stage is COMPLETE only when the persisted 9G agent-key roster contains `skeptic`. If the multi-model council exposes `skeptic_escalation_recommended`, that value is displayed as a separate persisted council artifact.

**RAW SKEPTIC TEXT NOT EXPOSED BY READ-ONLY CONTRACT.**

### Committee

The theater displays the persisted Committee disposition, confidence, headline/summary when exposed, decision id, and persisted multi-model council packet/views when available.

### Risk

The theater displays persisted deterministic Risk decision, authorization id and triggered rules when exposed.

### Paper

Only a persisted governed paper execution counts as a Paper-stage artifact. The theater repeats that this is PAPER and displays `LIVE EXECUTION FALSE`.

### Monitoring

The theater displays the persisted monitor status, snapshot time, latest return and thesis flags when exposed. Missing monitoring state remains WAITING.

### Outcome

The theater matches the selected ticker to persisted 9J outcome memory. The current 9J browser contract is canonical and exposes `market_outcome`, `longest_available_horizon`, `forward_return_pct`, `benchmark_return_pct`, `relative_return_pct`, `benchmark_source`, and `measured_at`. These current persisted fields are ordered first in the read-only browser artifact summary so the measured horizon and benchmark-relative result stay visible.

For compatibility with older experience components, the sidecar adds `market_outcome_label`, `decision_quality_label`, and a fixed-horizon return alias only when that alias is mathematically supported by `longest_available_horizon`. For example, a persisted 5-day measurement may populate `return_5d_pct`; a persisted 20-day measurement may populate `return_20d_pct` and must never be mislabeled as a 5-day return.

If the outcome has not matured, the room stays WARM-UP.

### Learning

The theater displays the persisted 9J `decision_quality` and `market_outcome` state. Legacy `*_label` aliases are derived from those current fields only for read-only experience compatibility. The theater has no authority to change thresholds, weights, Committee logic or Risk rules.

## Replay integrity

The browser controls are deliberately labeled:

`REPLAY CURSOR ONLY · DOES NOT EXECUTE FACTORY`

and

`NO FACTORY COMMANDS SENT`

The replay can:

- select a persisted governed case;
- jump to a persisted stage;
- advance backward/forward;
- auto-advance the **UI cursor** for presentation;
- inspect source ids and exposed artifacts.

The replay cannot:

- rerun a specialist;
- create or alter evidence;
- rerun Committee;
- change a Committee decision;
- rerun or bypass Risk;
- create a paper order;
- update monitoring;
- manufacture an outcome;
- change a 9J label;
- connect a broker;
- grant live-capital authority.

## Signal provenance

Case cards preserve the 9L four-badge contract:

- `JESSE DISLOCATION`
- `9E RADAR`
- `BOTH`
- `MANUAL / OTHER`

`BOTH` remains a persisted ticker overlap observation only. It does not assert causal linkage between Jesse logic and 9E.

## Browser composition

9N is additive. The browser keeps:

- 9L Living Factory Experience + provenance;
- 9M Character & Story Engine;
- 9K validation stack;
- existing Factory Intelligence UI.

It adds the Interactive Case Theater as a separate, reversible experience layer.

## Safety boundary

- Backend 8002: unchanged.
- 9A / 9B / 9E workers: unchanged by activation.
- 9G / 9H / 9I / 9J LaunchAgents: hash-protected by activation.
- Direct ledger access: none.
- Backend access through sidecar: allow-listed GET only.
- Backend write permission: false.
- Replay authority: UI cursor only.
- Trade execution permission: false.
- Broker connected: false.
- Live execution: false.

## Activation

The dedicated macOS activator uses the same preview address:

`http://127.0.0.1:5176`

Run from the live checkout after the branch is available locally:

```bash
python scripts/activate_batch9n_interactive_case_theater.py
```

It creates/refreshes an isolated 9N worktree, builds the browser, confirms the existing Backend 8002 read-only aggregation contract, replaces only the browser-preview LaunchAgent, checks the inherited living safety contract, verifies protected 9G–9J LaunchAgent hashes, and confirms the live checkout was not changed.

## Acceptance gate

9N is accepted when:

- exact ten-stage replay chain is present;
- case library contains only persisted governed cases;
- 9L provenance and 9M story layers remain composed;
- browser calls only same-origin `/living/overview` and `/living/case/{case_id}` for the theater;
- raw agent/Skeptic text is never fabricated;
- current 9J outcome fields are preserved as canonical browser data;
- any legacy fixed-horizon aliases are added only for the actually measured horizon;
- replay controls are cursor-only;
- TypeScript build and ESLint pass;
- 9J regressions and inherited 9K/9L/9M contracts remain green;
- no direct ledger or backend write path is introduced;
- Backend 8002 remains unchanged;
- trade execution permission remains false;
- live execution remains false.

## Next batch

**9O — Daily Factory Episode** will turn persisted daily activity into an end-of-day factory episode/report covering best calls, misses, saves, bad calls, governed paper performance, what was learned and the next session's focus. The same event-grounding rule remains: no persisted evidence, no storyline claim.
