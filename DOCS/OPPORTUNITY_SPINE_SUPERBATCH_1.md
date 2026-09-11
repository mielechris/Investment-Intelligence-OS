# Opportunity Spine Superbatch 1

This is an offline source contract extension. BASELINE_ONLY and the accepted
Monday readiness implementation remain unchanged. No mode is installed, armed,
qualified, or granted an account allowance by these modules. Runtime and session
authority identities are explicitly null. A future reviewed implementation commit,
its complete source inventory and runtime must be independently pinned before
any native/live adapter is permitted. Synthetic GREEN means offline contract
completion only, never market-session or provider readiness.

## Scope and modes

`opportunity_spine_contract` builds a deterministic Monday September 14, 2026
schedule using the existing independently pinned calendar and ordered 517-member
universe. It preserves the existing readiness plan through its parent hash.
BASELINE_ONLY has the ten-symbol preflight and three six-request checkpoints;
FULL_OPPORTUNITY_RADAR has the same preflight and 79 six-request scans at five-minute
intervals from 06:30:30 through 13:00:30 PDT. Each full scan has an exclusive
five-minute completion deadline; the final proposed deadline is 13:05:30 PDT.
That requires a new authority expiration covering completion and shutdown; an old
13:05 authority is insufficient. Baseline intervals retain their existing bounds.

Batches remain 100/100/100/100/100/17 in governed order. Response reordering is
rejected, even with complete membership. The explicit contract admits one pending
reservation only, counts starts before completion, bounds each response to twenty
seconds and one million bytes, rejects fourth starts inside a rolling minute,
and stops on partial, expired, malformed, stale, future or ambiguous observations.
A pending reservation cannot be recovered into another dispatch; interruption
retains consumption. There is no retry, redirect, pagination, provider fallback,
backfill, native dispatcher, scheduler, credential resolver or disk persistence
implementation in this extension. Existing gateway live admission does not accept
this new full-radar schedule. That boundary is deliberate pending qualification.

The full session proposes 475 calls: one preflight plus 474 collection calls.
This is not released by the documented account ceiling of 150/minute. Request
starts remain capped at three/minute, substantially below that account ceiling.
Payload size bounds aggregate to 475,000,000 bytes, processed ephemerally. A scan
is an interval with six separate dispatch/response/provider timestamps, never an
atomic snapshot. The Alpha contract remains distinct from independent Yahoo
observations; no Alpha missing coverage can be repaired by Yahoo.

## Signals and promotion

The signal engine receives synthetic payloads through the same offline batch
admission function, using ephemeral memory only. It emits derived percentages,
boolean flags, timestamps, counts and missing-field codes, never raw payloads,
prices, provider free text, response hashes or credential values. Optional numeric
fields are validated before use. Previous-close and average-volume absence remain
null. Session high/low outputs mean *at observed session high/low*, not retained
quote values. Opening range is the first admitted scan's observed range; it is not
claimed to be an exchange tick-complete opening range. Volume metrics compare the
provider's observed fields; they do not assert five-minute incremental volume
without that schema being established. Volatility expansion compares successive
observed high/low percentage ranges. Baseline mode does not label widely spaced
observations as five-minute returns.

SPY/QQQ relative strength is available only if those symbols are in the same
admitted universe/scan. No supplementary benchmark request is generated. Governed
sector membership is separately hash-pinned; sector divergence uses the mean
session return of available governed same-sector peers. Missing peers remain null.
New detection policy `opportunity-signals-v1` uses an inclusive one-percent
five-minute move and two consecutive same-direction detections for persistence;
a reversal resets persistence. These are versioned proposed detection thresholds,
not a substitute for existing research-promotion eligibility.

Read-only source review found:

* `high_speed_market_radar.py`: at most five promotions and two agent cases per
  cycle; default twelve-hour duplicate-case cooldown (configurable one to 72).
* `opportunity_acquisition.py`: score at least 45, at least two news items and a
  valid quote for promotion; queue and legacy scan cap 20; HIGH priority at 65.
* `opportunity_scheduler.py`: default maximum ten candidates, one auto-dispatch,
  minimum 240-minute legacy automation interval. This scheduler is not modified.
* `expansion_wing/candidate_enrichment_bridge.py`: maximum five candidates and
  maximum five new credits; bridge disabled by default. It is not activated here.

The new promotion contract retains the radar's tighter five/two caps and default
12-hour cooldown and independently admitted legacy eligibility. No actual installed
configuration was read. Operational release must pin its effective limits; a tighter
owner setting must not be expanded to these defaults. Ordering is deterministic
universe order, not model ranking or averaged model opinions. Maximum daily bounds
395 promotions/158 cases are arithmetic capacity bounds before cooldown and evidence
blocks, not promises of opportunities or authorization to launch cases.

## Provider and factory connection

Roles remain Alpha quantitative scanning, Yahoo independent discovery, future
qualified Alpaca tape/paper-account validation, Financial Datasets corporate facts,
Bigdata research, and Massive Basic historical/end-of-day/reference validation.
No provider is automatically activated. Proposed per-case routes permit at most
one request per provider; Alpha, Financial Datasets and Bigdata evidence are
required in routing-policy v1, the other three optional. Every unexecuted stage
starts NOT_RUN. Bigdata retention qualification remains required. A required
missing provider blocks only that case.

The factory connects independently pinned candidate, route, evidence, agent,
Committee and deterministic Risk receipts. Legacy factory modules are not imported:
they import operational ledgers and live model clients. This source boundary makes
no claim that native factory adapters have been qualified. Existing evidence owners
must substantively accept evidence before supplying trusted hashes. A self-hash
alone is not an independent pin. All received stage parents must equal the complete
preceding stage chain for the same case and requirement plan.

The existing eight-agent identity is policy, macro, fundamentals, market_structure,
commodities, geo_weather, skeptic and portfolio. Skeptic is already one of eight;
it is not silently counted twice. OpenAI coordination, Grok and Gemini challenger
stages remain distinct. No model establishes evidence truth or Risk. Model
conclusions remain separate; there is no model averaging. A Committee approval
cannot override a Risk veto. WATCH, NO_TRADE and zero candidates are legitimate.
Outcome eligibility is evaluation eligibility only; no order authority follows.

Capacity proposes at most six enrichment requests and twelve model calls per
case (eight agents including Skeptic, Committee, OpenAI coordination, Grok, Gemini;
deterministic Risk zero model calls). Upper bounds for 158 cases are 948 enrichment
requests and 1,896 model calls. None are budget-authorized. Enrichment credential
lookup bound is seven per case because Alpaca requires two selectors; caching
could reduce actual access. Alpha bound is one lookup per attempted call. Model
credential access and monetary prices remain unresolved until a pinned model
runtime and billing plan exist. Yahoo usage is recorded input or unknown, never a
fabricated estimate or additional dispatch. Ambiguous consumption stays reserved.

Final session joins retain sanitized collection, scan, signal, candidate, routing
and case stage receipts. Required parent hashes, IDs and backend/frontend identity
must match. Collection failure or omitted scans is RED; unavailable Yahoo or blocked
cases is YELLOW; complete offline evidence can be GREEN without producing trades.
Every receipt fixes broker_connected, paper_order_permission,
trade_execution_permission, live_execution and ledger_write_authority to false.

`opportunitySpine.ts` is a strict read-only contract admission module, not a UI or
network poller. It exposes mode, coverage/freshness, Yahoo status, signal/candidate
counts, cases, provider/agent/model statuses and Committee/Risk decisions, with
independent backend/frontend/session/source/hash checks. Existing Northstar
artwork, navigation and baselines are untouched. Native backend publication and
UI mounting require separately reviewed adapters. Hercules stays outside truth.

## Validation and next authority

Tests use synthetic symbols, controlled clocks and mocked stage receipts only.
No actual account, provider, model, ledger or service evidence is used. Test output
and exact source inventory are retained in the separate source-test root. A test
failure stops this batch; no failure is excluded or converted to success.

Checkpoint proposal: after all mandatory offline gates pass and the exact inventory
is reviewed, stage only these seven new files, commit normally with hooks enabled,
and push non-force to the existing branch. This batch does not grant that authority.

Native/live proposal must independently pin the implementation, runtime/TLS/address,
ordered Monday universe, model/provider account evidence and usage/retention rights,
effective promotion/cooldown limits, source-to-runtime adapter identities, native
ownership/cleanup proof, and a new Monday authority through at least 13:05:30 PDT
plus bounded shutdown. Release 475 Alpha calls only through separate account/cost
and execution authorization. First qualify bulk preflight during 06:20–06:25 PDT;
any authentication, schema, timestamps, coverage or freshness failure cancels all
collection. No previous GLOBAL_QUOTE receipt substitutes for bulk qualification.
Yahoo collection remains unchanged. Missing native adapters, factory evidence,
retention permission or independent pins remain blockers to unattended readiness.
