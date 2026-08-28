# Batch 9M — Character & Story Engine

## Purpose

Batch 9M gives MAX and the eight IIOS specialist characters durable personalities, recognizable voices, debate and dark/adult factory humor **without allowing the story layer to invent market activity**.

Batch 9M is a narrative rendering layer on top of the green Batch 9L living factory. It does not become a source of investment evidence and it does not write to IIOS.

## Governing rule

> No persisted event means no dialogue.

Every rendered story beat must be anchored to a persisted 9G meaningful audit event. The browser displays the event type, case id, entity id and event timestamp alongside the rendered dialogue.

The dialogue is explicitly labeled **narrative rendering, not raw agent output**. A character line is allowed to interpret or react to the persisted state in that character's established voice, but it may not claim that an order, decision, completion, outcome or market fact occurred unless the supporting persisted event/state exists.

## Persistent cast bible

### MAX — Factory Foreman

- Temperament: gruff, decisive, irreverent, allergic to fake certainty.
- Mantra: `Evidence first. Ego gets a folding chair.`
- Voice: plain English, dark humor, disciplined about governance.

### Policy Analyst — Regulatory Bloodhound

- Temperament: literal, skeptical of political theater, obsessed with transmission mechanisms.
- Mantra: `A headline is not a causal chain.`

### Macro & Rates Analyst — Regime Obsessive

- Temperament: cool-headed, probabilistic, skeptical of one-factor explanations.
- Mantra: `Rates have friends. Find them.`

### Fundamentals Analyst — Numbers Before Vibes

- Temperament: dry, forensic, unimpressed by narrative without financial support.
- Mantra: `Good company and good price are different species.`

### Market Structure Analyst — Tape Reader

- Temperament: fast, sardonic, watches price behavior before believing the story.
- Mantra: `The tape can throw a chair without explaining why.`

### Commodities & Supply Chain Analyst — Physical-World Realist

- Temperament: practical, seasonal, skeptical of models that ignore real supply constraints.
- Mantra: `You cannot spreadsheet a missing truck, crop or barrel into existence.`

### Geopolitics & Weather Analyst — Scenario Disciplinarian

- Temperament: calm around ugly scenarios; strict about confirmed fact versus tail risk.
- Mantra: `Drama is not probability.`

### Skeptic / Red Team — Professional Buzzkill

- Temperament: adversarial, darkly funny, happiest when a weak thesis dies before capital sees it.
- Mantra: `Cute thesis. Now tell me how it dies.`

### Portfolio Context Analyst — Risk-Adjusted Adult

- Temperament: blunt and capital-aware; refuses to confuse being right with sizing intelligently.
- Mantra: `A good idea can still be a stupid position.`

## Event vocabulary

The current 9G telemetry contract exposes these meaningful persisted audit events:

- `OPPORTUNITY_PROMOTED_TO_CASE`
- `COMMITTEE_COMPLETE`
- `RISK_COMPLETE`
- `GOVERNED_PAPER_ORDER_CREATED`
- `AUTO_MONITOR_FAILED`
- `OPPORTUNITY_AUTOMATION_CYCLE_FAILED`
- `HIGH_SPEED_MARKET_RADAR_COMPLETE`

9M contains explicit deterministic narrative handling for all seven. Unknown future event types fall back to a factual MAX line that states only the event identity and refuses to add story beyond the persisted record.

## Debate behavior

The theater turns one persisted event into a small character exchange.

Examples of the pattern:

- Promotion → MAX acknowledges the governed promotion; Skeptic attacks the thesis; Market Structure points back to persisted radar score when available.
- Committee → MAX states persisted disposition/confidence; Skeptic reacts to that disposition without changing it.
- Risk → Portfolio Context states the persisted Risk decision; MAX reinforces that the governed state cannot be bypassed.
- Paper order → MAX explicitly says this is PAPER; Portfolio Context frames it as a future measurement point, not a win.
- Monitor/automation failure → MAX and Skeptic identify the operational failure as operational, not a market signal.
- Radar cycle → Market Structure states the persisted scanned/queued/promoted counts; Skeptic treats a quiet cycle as valid data rather than pressure to manufacture activity.

## What 9M does not do

9M cannot:

- write ledger objects or audit events;
- call Backend 8002 directly from the browser;
- POST/PUT/PATCH/DELETE any API;
- change opportunity scores or promotion thresholds;
- change agent weights;
- change Committee logic;
- change Risk rules;
- create a paper order;
- connect a broker;
- grant live-capital authority;
- represent its narrative lines as historical raw model-agent speech.

The story component reads the same same-origin `/living/overview` contract introduced by 9L. That sidecar remains GET-only and maintains no direct ledger access.

## Visible browser result

The 9M browser keeps the complete 9L living factory and adds:

1. A persistent **Cast Bible** with MAX + all eight specialists.
2. Active-speaker highlighting driven by the selected persisted story beat.
3. A **Live Factory Story Feed** made only from recent 9G meaningful events.
4. An **Event-Bound Debate Theater** with adult/dark commentary.
5. Source event metadata on every debate.
6. Explicit `NO EVENT → NO DIALOGUE` and `LIVE EXECUTION FALSE` controls.
7. Continued 9G / 9H / 9I / 9J availability indicators.

## Activation

The 9M activator keeps the same localhost preview URL:

`http://127.0.0.1:5176`

It builds from an isolated 9M worktree, checks Backend 8002's existing read-only contract, replaces only the browser-preview LaunchAgent, validates the inherited 9L living safety contract, verifies that the protected 9G/9H/9I/9J LaunchAgents did not change, and checks that the live IIOS checkout remained untouched.

## Acceptance gate

9M is accepted when:

- the 9L regression and safety contracts remain green;
- all current 9G meaningful event types have explicit story handling;
- the cast contains MAX plus exactly eight specialists;
- character dialogue reads only `/living/overview`;
- no direct backend URL or write method exists in the story component;
- the browser build and ESLint pass;
- no direct ledger access is introduced;
- Backend 8002 remains unchanged;
- protected 9G/9H/9I/9J workers remain unchanged;
- broker connection remains false;
- trade execution permission remains false;
- live execution remains false.

## Next batch

**9N — Interactive Case Theater** will take the same provenance and event-bound narrative contracts and allow a governed replay of one opportunity from discovery through research, eight-agent debate, Committee, Risk, paper decision, monitoring and eventual learning outcome.
