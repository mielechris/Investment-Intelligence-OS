# IIOS Provider Gateway — source-only Superbatch 1

IIOS remains the sole truth and decision authority. This checkpoint implements a
governed offline gateway with six public-data adapter contracts, normalized
receipts, a readiness projection, three Monday checkpoint plans and an offline
stage evaluator. It contains no operational HTTP transport, credential retrieval,
model call, service entry point, broker client or order submission. No provider
is operationally GREEN because these contracts exist or a synthetic API responds.

## Locked provider roles

| Provider | Role |
|---|---|
| Financial Datasets | Corporate facts, statements, metrics, filings and price history |
| Alpaca data | Authoritative market truth/validation; explicit SIP/IEX/delayed/unavailable feeds |
| Alpaca paper | Separate, later governed PAPER-ONLY rail; all permissions false here |
| Massive | Independent broad-market validation, complete-universe snapshots and advanced feed |
| Alpha Vantage | Specialist enrichment and secondary confirmation |
| Bigdata.com | Grounded research, news, filings, transcripts, catalysts and narrative evidence |
| Yahoo | Existing five-minute discovery and benchmark; never authoritative universe coverage |
| OpenAI | Orchestration and structured reasoning |
| Grok / Gemini | Independent narrative / long-context challengers |
| GitHub / Codex | Engineering, CI and release provenance |
| Hercules | Unpublished read-only UX/testing outside truth; no provider calls |
| Northstar | Official IIOS browser presentation; no visual changes |

## Integration boundary and source scope

Base: the synchronized Truth Spine checkpoint
`131a3ee1f54f1d3ab77fbf0ebe791068ffb9e719`. This keeps its strict SQLite repair.
Only the pure `truth_spine_contract` canonical/hash/time functions are imported.
The existing ledger-coupled scheduler and date-bound provider-readiness services
are not imported, replaced or edited. Their operational migration remains a
separate source/integration review. Existing legacy agents are not globally
rewired by this batch: the new flow supplies only promoted observations to
callbacks and never gives them a gateway, credential or transport. Confinement
of future real model/transport implementations still requires runtime review.

Ten new files implement this scope: four modules (`provider_gateway_contract`,
`provider_gateway_adapters`, `provider_gateway`, `market_baseline_plan`), their
four test modules, `config/provider-gateway-monday.json.template`, and this
document. No existing collector, selector, service, ledger, frontend, artwork,
fixture, screenshot or dependency file changes. The previous sequential Yahoo
draft and review evidence remain untouched and uncheckpointed.

## Adapter and receipt contract

The gateway admits independently hash-pinned policy, universe and request
documents. A request must match the qualified endpoint, exact symbol membership,
explicit feed and mode, validity window, rate/cost/rights qualifications and
bounded response/age/deadline limits. The policy is OFFLINE_ONLY; missing inputs
fail before transport. There is no implicit provider, feed or retry fallback.
Reservations are in-memory and single-use for these synthetic tests only, with
at most three requests per provider per gateway instance. They must not be used
as a live, durable cost reservation or evidence of production rate enforcement.

Massive and Alpaca accept their public snapshot JSON shapes. Corporate adapters
accept a versioned logical transport projection, `records`, rather than claiming
that every provider endpoint returns that envelope. Endpoint-specific secure
wire decoders and their raw-byte bindings must be qualified before live use.
Financial Datasets covers the ten pilot instruments MU, SPY, XLK, VNQ, TLT, GLD,
UUP, IBIT, PFF and BIL. ETF company sector/industry are unavailable, never inferred.
Bigdata preserves source references and observation/publication/retrieval times;
no narrative directly creates a Committee decision. Alpha Vantage is secondary.
Yahoo normalization preserves candidate order and selection without running its
collector. Screener returns and governed-universe size are separate quantities.

Every receipt records provider/role/adapter version, endpoint, policy/universe/
request parents, symbol sets and hashes, duplicate/missing/unexpected symbols,
field absence, status/partiality/delay, original provider timestamps, request and
receipt times, feed/tier, freshness, provenance, admissibility, entitlement,
cost uncertainty, retry count and locked operational authority. The raw-response
content hash is the canonical public JSON transport body, not an HTTP wire-byte
hash. Observation hashes use the existing Truth Spine canonical format. Original
integer timestamps retain full precision; derived ISO values have microsecond
precision. No missing provider timestamp is synthesized from arrival time.

Secret-bearing keys/URLs are rejected before hashing/writing; untrusted exception
and error text is not emitted. Injected transports must never receive or return
credentials. This is not a claim that arbitrary unlabeled text can be proven
secret-free: future live secure transports require credential redaction tests
and field-specific wire decoding. This batch retrieves no secrets.

Owner-only receipt directories are opened with no-follow directory descriptors;
files use exclusive creation and fsync. Existing paths cannot be overwritten.
Failed/partial writes are retained. No cleanup deletion is implemented.

## Governed downstream stages

Normalized provider observations -> provenance/freshness/admissibility ->
governed evidence -> independently pinned promoted candidates -> agents/models
-> Johnny No/Skeptic -> Committee -> deterministic Risk -> Alpaca PAPER decision
-> receipt -> outcome learning.

This is an offline evaluator of that ordering, not a second production decision
engine. Supplied synthetic stage callbacks return their independently expected
parent identity. A missing stage, wrong parent, invalid/stale evidence or failed
stage blocks later stages as NOT_RUN. The primary gate requires Alpaca SIP;
Massive, research, enrichment or Yahoo cannot replace it. Provider disagreement
is retained by provider without averaging it into truth. No callback receives
unpromoted observations. Even all PASS returns NO_EXECUTION_OFFLINE; no execution
outcome is invented for learning. Committee PASS plus Risk FAIL cannot execute.

Admissible offline evidence is not operational readiness. API success does not
confirm billing; observed cost stays UNVERIFIED in these adapter contracts.
The readiness matrix always leaves credential binding and runtime integration
UNVERIFIED and operational authority LOCKED_FALSE. Caller GREEN labels or linked
ChatGPT connectors cannot override those gates. No aggregate operational GREEN
is available from this source-only checkpoint.

## Monday plan

Require an independently pinned, unique 517-symbol universe and Monday XNYS
calendar record. No universe download or calendar service is invoked. Targets:

| Checkpoint | PDT | UTC |
|---|---|---|
| Opening | 06:30:30 | 13:30:30 |
| Intraday | 09:30:00 | 16:30:00 |
| Closing | 13:00:30 | 20:00:30 |

Each target has a 30-second dispatch window and 20-second response deadline.
Missed observations remain missed/partial; never backfill. Three proposed bulk
requests do not imply three credits. Snapshots are not atomic exchange captures
or auction-price proof. Feed delay remains distinct from field age; unchanged
prices alone never establish staleness. Filtered mode is an explicit preselected
alternative, not a response-failure fallback. Yahoo discovery remains unchanged.

## Validation and remaining release gates

Run focused gateway/adapter/receipt/plan tests with synthetic inputs, plus existing
affected Truth Spine canonical and Expansion Wing enrichment regressions under
network/process denial. Compile changed Python, check deterministic receipts,
scoped AST/import/secret/private-path/authority/whitespace scans, and preserve all
outputs. No frontend types changed, so TypeScript/frontend tests are unaffected.
There is no repository Python lint configuration; report exact scoped checks
rather than claim an unavailable linter ran. No CI workflow is changed.

Every provider still needs current independent endpoint, symbol/field entitlement,
feed, commercial/internal-use, rate/cost/billing and non-secret selector/account
binding evidence. Before live qualification: reviewed secure wire transport,
qualified runtime/TLS/host allowlist, persistent request accounting, redaction,
timeout/cleanup and source-bound receipts. Before Monday installation: accepted
source/release/runtime/TLS/startup hashes, exact roots, process ownership,
calendar/universe/account/reservation pins, bounded authority expiration,
noninterference, duplicate/startup/shutdown tests and a separate owner execution
authorization. No existing runtime or historical account receipt supplies these
permissions implicitly.
