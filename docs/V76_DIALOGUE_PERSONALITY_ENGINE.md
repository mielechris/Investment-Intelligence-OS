# V7.6 Dialogue + Personality Engine

## Frozen visual base

V7.6 branches from the frozen V7 visual-canon checkpoint at commit:

`4fe4aec55953be73da7285c132910d8c2c983e52`

Checkpoint branch:

`checkpoint/v7-visual-canon-frozen`

The approved Family Wall, nine individual character portraits, V7.5.2 avatar integration polish, and MAX small-scene sizing fix are treated as frozen visual canon for this batch.

## Objective

Give the recurring IIOS cast consistent, differentiated presentation voices without changing the authoritative IIOS state model.

V7.6 adds:

- a nine-character personality bible;
- character-specific cadence and domain obsessions;
- larger phrase banks to reduce repetition;
- event-category-specific dialogue for promotion, research, committee, risk, paper, monitoring, learning and failure receipts;
- room-specific language;
- deterministic alternate presentation takes;
- receipt continuity callbacks;
- explicit family rivalries and inter-character jabs;
- a visible Dialogue Room for reviewing personalities and generated presentation takes against real persisted receipts;
- backward-compatible `mobVoice` routing so existing V7.2/V7.3/V7.4 presentation components inherit V7.6 specialist dialogue.

## Character canon

### MAX

Mob-boss factory foreman. Short orders, irritated punchlines, evidence/downside obsession, no live-capital funny business.

### Frankie Fine Print

Regulatory consigliere. Fine print, effective dates, authority, exceptions, literal rule text.

### Benny Basis Points

Rates/regime obsessive. Yield curve, Fed, dollar, liquidity, discount-rate consequences.

### Vinny EBITDA

Cash-flow enforcer. Margins, earnings quality, valuation, balance sheet, cash conversion.

### Mikey Tape

Tape-reading street operator. Flow, positioning, trapped holders, liquidity, volatility.

### Tony Tanker

Physical-market bruiser. Inventory, freight, storage, physical supply, basis.

### Stormy Sal

Scenario prophet. Weather, war, chokepoints, shipping lanes, ugly branches of the scenario tree.

### Johnny No

Thesis assassin. Falsifiers, contradictions, hidden assumptions, base-rate failure.

### Paulie Positions

Risk-adjusted adult. Sizing, correlation, drawdown, exposure and survival.

## Truth boundary

Persisted IIOS receipts remain authoritative.

V7.6 dialogue is presentation-only and must never be represented as:

- raw model output unless raw output is explicitly present and labeled;
- new evidence;
- a committee disposition;
- a risk decision;
- paper execution state;
- live execution authority;
- live-capital authority;
- backend write authority.

A new presentation take changes wording only. It does not change receipt facts.

## Anti-repetition

Dialogue selection is deterministic. The engine hashes receipt/event context and presentation-take seeds rather than using `Math.random()`.

This gives stable wording for a given take while allowing a user to request another presentation take without manufacturing a new market event.

## Continuity

When a prior persisted receipt for the same case/ticker is visible in the current persisted window, V7.6 may reference its event type as presentation continuity. It does not invent hidden history.

## Rivalries

Relationship lines are presentation flavor only. They are never evidence of literal model-to-model conversation.

Examples include Johnny vs. Vinny, Benny vs. Frankie, Mikey vs. Vinny, Tony vs. Benny, Sal vs. Tony, and Paulie vs. Johnny.
