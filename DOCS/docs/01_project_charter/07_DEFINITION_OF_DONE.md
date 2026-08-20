# Investment Intelligence OS
## Definition of Done — v0.1

**Purpose:** Define the minimum evidence required before any document, ticket, connector, service, agent, model, strategy, paper-trading component, or release may be called complete.

“Code exists” is not done.  
“An AI produced an answer” is not done.  
“A backtest made money” is not done.

---

## 1. Universal Definition of Done

Every completed item must have:

- a clear purpose;
- an owner;
- documented inputs;
- documented outputs;
- documented dependencies;
- documented failure modes;
- acceptance criteria;
- a happy-path test;
- at least one failure-path test;
- logging or traceability;
- security and data-boundary review;
- risk review appropriate to impact;
- documentation;
- an Engineering Log entry;
- linked tickets and specifications;
- no unresolved critical defect;
- versioned changes.

---

## 2. Documentation Done

A governing or technical document is done when:

- title, version, date, owner, and status are present;
- purpose and scope are explicit;
- terms are consistent with the glossary;
- contradictions with higher-level documents are resolved;
- decision rights are clear;
- assumptions and exclusions are stated;
- review trigger is stated;
- links to related documents are valid;
- Markdown renders cleanly;
- material changes are recorded in the Decision Register;
- approval status is explicit.

---

## 3. Data Connector Done

A source connector is done when:

- source identity and rights are documented;
- endpoint or retrieval method is configured;
- secrets are not hard-coded;
- raw payload is stored immutably;
- retrieval time is recorded;
- published, effective, observed, and market-available times are handled where relevant;
- parser output follows the canonical schema;
- deduplication works;
- revisions are handled;
- source failures are logged;
- stale data is detected;
- rate limits and retries are handled;
- malformed data is quarantined;
- happy-path fixture test passes;
- failure-path test passes;
- historical replay is possible;
- source health appears in monitoring.

---

## 4. Canonical Schema Done

A schema is done when:

- field meanings are documented;
- required and optional fields are explicit;
- identifiers are stable;
- timestamps are timezone-aware;
- validation rules exist;
- versioning rules exist;
- backward-compatibility impact is reviewed;
- sample valid and invalid records exist;
- serialization and deserialization tests pass;
- database mapping is defined;
- provenance linkage is preserved.

---

## 5. Service Done

A service is done when:

- API or function contract is documented;
- inputs and outputs are typed;
- authorization boundary is defined;
- idempotency is considered;
- retries do not duplicate state;
- failure behavior is deterministic;
- logs contain correlation IDs;
- metrics and health checks exist;
- unit tests pass;
- integration tests pass;
- a failure-path test exists;
- configuration is externalized;
- no secrets are committed;
- deployment and rollback are documented.

---

## 6. Agent Done

An AI agent is done when:

- mandate is explicit;
- prohibited behavior is explicit;
- permitted tools and data are explicit;
- required source evidence is explicit;
- output schema is structured;
- confidence and uncertainty are represented;
- abstention is supported;
- prompt and model versions are recorded;
- hallucination and unsupported-claim tests exist;
- adversarial and contradictory cases are tested;
- cost and latency are measured;
- authority is bounded;
- no direct live-order permission exists;
- output can be audited and reproduced sufficiently for review;
- calibration is tracked over time.

---

## 7. Committee Done

The Investment Committee is done when:

- required agent inputs are defined;
- missing inputs block or lower confidence;
- dissent is preserved;
- the skeptic view is visible;
- no-trade is supported;
- rationale is structured;
- linked evidence is required;
- unresolved assumptions are visible;
- committee output cannot place an order directly;
- deterministic test cases cover candidate, no-trade, and conflict outcomes.

---

## 8. Risk Component Done

A risk component is done when:

- limits are explicit and configurable;
- risk has veto authority;
- concentration is checked;
- correlation or theme overlap is checked;
- liquidity is considered;
- drawdown states are tested;
- stale critical data disables new risk;
- kill-switch behavior is tested;
- override authority is documented;
- every risk decision is logged;
- portfolio accounting reconciles.

---

## 9. Backtest or Strategy Done

A strategy test is done when:

- hypothesis is written before final evaluation;
- point-in-time data is used;
- leakage tests pass;
- benchmark is included;
- fees, spreads, slippage, and turnover are included;
- train, validation, and holdout or walk-forward structure is used;
- parameter sensitivity is shown;
- sample size is reported;
- hit rate, average win/loss, drawdown, volatility, turnover, and concentration are reported;
- regime performance is reported;
- gross and net results are reported;
- failed versions are preserved;
- reproducible code and configuration exist;
- forward paper-test requirement is defined;
- promotion decision is recorded.

---

## 10. Paper Trade Done

A paper trade is valid when:

- a thesis exists;
- evidence links exist;
- committee disposition exists;
- risk approval exists;
- position size is within limits;
- simulated order assumptions are recorded;
- fill, spread, fees, and slippage are recorded;
- portfolio state reconciles;
- invalidation and exit logic are recorded;
- position is visible in the command center;
- journal entry exists;
- outcome and postmortem are scheduled.

---

## 11. Dashboard Done

A dashboard panel is done when:

- its source of truth is identified;
- stale data is visibly marked;
- timestamps are visible;
- empty, error, and stand-down states are designed;
- values reconcile with backend records;
- no material decision exists only in the UI;
- links to evidence and journal records work;
- loading and failure behavior are tested;
- the owner can understand the panel without reading code.

---

## 12. Release Done

A release is done when:

- all included tickets meet their own Definition of Done;
- tests pass;
- migrations are tested;
- secrets are reviewed;
- release notes exist;
- version is assigned;
- rollback is tested or documented;
- backup status is verified;
- critical monitoring is active;
- known limitations are listed;
- the Decision Register and Engineering Log are updated;
- paper/live mode is displayed correctly;
- no live authority is enabled accidentally;
- the founder approves the release where required.

---

## 13. “Not Done” Conditions

An item is not done when:

- it works only on the developer’s machine without instructions;
- it has no test;
- it has no failure behavior;
- it cannot be traced;
- it relies on future data;
- it hides uncertainty;
- it bypasses risk;
- it uses unapproved information;
- it silently changes a schema;
- it silently changes a model or prompt;
- it produces an unexplained trade;
- it continues through a critical feed failure;
- it has an unresolved critical security defect;
- it is described as done only because a demo looked good.
