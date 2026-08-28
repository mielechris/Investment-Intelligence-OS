# Batch 9O — Daily Factory Episode

## Purpose

Batch 9O gives IIOS an evidence-grounded end-of-day episode/report without turning storytelling into an investment authority.

The episode answers seven daily questions from persisted IIOS state:

1. What were the best measured calls?
2. What bad outcomes did governance save us from?
3. What did the factory miss?
4. Which calls belong in the dumb-call file?
5. How did the governed paper book perform?
6. What did 9J actually learn?
7. What should humans review tomorrow?

No category is assigned from vibes. Best calls, saves and adverse calls use the exact persisted Batch 9J `decision_quality` labels. Validation misses use Batch 9H opportunity rows. Tomorrow's focus can include Batch 9I shadow recommendations, but those remain advisory only.

## Source chain

9O reads local sidecar/report state only:

- **9G** — factory telemetry, provider health, governed paper snapshot.
- **9H** — independent market-validation opportunities, detection/miss metrics.
- **9I** — shadow counterfactual recommendations.
- **9J** — current outcome-learning schema including `decision_quality`, `market_outcome`, measured horizon and benchmark-relative returns.

It has no direct ledger access and does not call Backend 8002 to write anything.

## Deterministic classification

### Best Calls

Current favorable 9J labels:

- `PAPER_ENTRY_FAVORABLE`
- `WATCH_VALIDATED_BY_UPSIDE`

### Saves

Current downside-avoidance label:

- `NO_TRADE_AVOIDED_DOWNSIDE`

### Dumb Calls

Current adverse/foregone-upside labels:

- `PAPER_ENTRY_ADVERSE`
- `WATCH_FALSE_POSITIVE_OR_REVERSAL`
- `NO_TRADE_FOREGONE_UPSIDE`

The product label is intentionally informal because this is the factory story layer; the underlying classification remains the exact persisted 9J label.

### Misses

Primary daily misses come from 9H opportunities that were not detected in the validation window. 9J `FACTORY_MISS_WITH_UPSIDE` outcomes are also retained in the learning-miss section.

The report does not award post-hoc credit to the factory for a benchmark move that was not actually detected.

## Paper performance

The episode reports the persisted 9G governed paper snapshot when available:

- starting cash;
- NAV;
- cash;
- market value;
- realized/unrealized/total P&L;
- gross exposure;
- position and transaction counts;
- cumulative return;
- current/max drawdown.

Paper performance is explicitly measurement only. Batch 9O cannot connect a broker or grant live-capital authority.

## Daily story

The episode contains a small evidence-bound MAX/Skeptic/Portfolio closing story. Every line has a `basis` field naming the persisted source that supports it.

Examples of allowed behavior:

- MAX can state the persisted 9H benchmark/detection/miss counts.
- Skeptic can react to a persisted `NO_TRADE_AVOIDED_DOWNSIDE` save.
- Skeptic can put a persisted adverse 9J decision-quality label in the "dumb-call file."
- Portfolio can state the persisted 9G paper NAV/P&L.

The story cannot claim an event, call, save, miss, fill, return or lesson that is absent from the source data.

## Live draft versus final episode

The browser always has something truthful to show:

### `LIVE_DRAFT`

Before the end-of-day final window, React derives a read-only draft from the current `/living/overview` persisted state. It is clearly marked as a live draft and is not written back into IIOS.

### `FINAL`

After **16:45 America/New_York** on a weekday, the Batch 9O worker builds the report from the local 9G/9H/9I/9J state and writes:

`~/Library/Application Support/IIOS/market-validation/browser/daily_factory_episode.json`

The publisher copies the final JSON into the isolated browser build as:

`FRONT END/dist/daily_factory_episode.json`

The browser switches from draft to final only when the persisted episode's `episode_session_id` matches the currently visible session.

### `FINAL_WITH_LEARNING_WARMUP`

If 9H is ready but 9J has not yet produced a matching current-session outcome set, 9O may write a final-with-learning-warmup artifact. The worker continues checking every 30 minutes and can replace it with `FINAL` once matching learning evidence is present.

## Tomorrow's focus

Tomorrow's focus is advisory only. It can include:

- review persisted 9H misses before considering any threshold change;
- inspect persisted 9I shadow recommendation(s);
- review 9G provider errors;
- collect more mature 9J outcomes;
- hold the governed baseline when no persisted evidence supports a change.

Every focus row contains an authority marker such as:

- `HUMAN_REVIEW_ONLY`
- `ADVISORY_ONLY`
- `OPERATIONS_REVIEW_ONLY`
- `NO_CHANGE`

9O never applies the proposed action.

## Automated worker

The isolated macOS LaunchAgent is:

`com.iios.daily-factory-episode`

It runs at load and every 1,800 seconds. The episode builder itself fails closed before the 16:45 ET final window and on weekends, so the periodic worker does not create a premature final report.

The worker writes only local report/browser artifacts. It does not restart or edit 9A, 9B, 9E, 9G, 9H, 9I or 9J.

## Browser result

9O adds a visible Daily Factory Episode room beneath 9N. It includes:

- status: LIVE DRAFT / FINAL / FINAL WITH LEARNING WARMUP;
- benchmark opportunities, detection rate and miss rate;
- paper NAV/P&L/positions/drawdown;
- 9J outcome count and maturity;
- evidence-grounded story lines;
- Best Calls;
- Saves;
- Dumb Calls;
- Misses;
- decision-quality memory;
- tomorrow's advisory focus;
- explicit safety/governance rail.

The full 9L Living Factory, 9M Character Story Engine, 9N Case Theater, 9K validation stack and existing Factory Intelligence UI remain composed.

## Safety boundary

- Backend 8002: unchanged.
- Direct ledger access: none.
- Backend write permission: false.
- Automatic threshold changes: false.
- Agent weight change authority: false.
- Committee change authority: false.
- Risk change authority: false.
- Capital authority: false.
- Trade execution permission: false.
- Broker connected: false.
- Live execution: false.

## Activation

From the live checkout after the branch is available locally:

```bash
python scripts/activate_batch9o_daily_factory_episode.py
```

The activator:

1. creates/refreshes an isolated 9O worktree;
2. builds and lints the browser;
3. runs a read-only episode preview and verifies its safety flags;
4. verifies Backend 8002's existing read-only factory status contract;
5. installs only the new 9O episode LaunchAgent;
6. replaces the existing localhost browser-preview LaunchAgent with the 9O build;
7. verifies the protected 9G/9H/9I/9J LaunchAgent hashes did not change;
8. verifies the live checkout branch/worktree did not change;
9. opens `http://127.0.0.1:5176`.

## Acceptance gate

9O is accepted when:

- deterministic classification tests pass;
- live draft is based only on `/living/overview`;
- persisted final is read only from the local static episode JSON;
- final worker reads only 9G/9H/9I/9J sidecar/report files;
- every story line has a persisted-source basis;
- exact adverse/favorable 9J labels are used;
- 9H misses are surfaced without post-hoc credit;
- 9I recommendations remain advisory;
- paper performance remains explicitly paper;
- all inherited 9K/9L/9M/9N contracts and factory-learning regressions stay green;
- frontend ESLint/build pass;
- protected 9G–9J workers remain unchanged;
- no backend write or execution authority is introduced;
- live execution remains false.

## Next batch

**9P — Chief Intelligence Office / Continuous Improvement Engine** will use these accumulated miss/call/outcome/shadow/provider/latency measurements to produce a formal advisory-only IIOS Improvement Memo with top upgrades, evidence, expected impact, effort, provider cost, safety risk, recommended environment and rejected ideas.
