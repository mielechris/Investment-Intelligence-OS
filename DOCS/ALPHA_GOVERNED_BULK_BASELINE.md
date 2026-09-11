# Alpha governed bulk baseline — source-only, not activated

The explicit REALTIME_BULK_QUOTES contract uses Alpha's fixed HTTPS query route,
real_time account feed and GOVERNED_REALTIME_MARKET_BASELINE role. Existing
GLOBAL_QUOTE qualification and SMA enrichment remain unchanged. Legacy generic
provider-role tables describe their original contracts; the bulk function has
an explicit role/endpoint/feed override, not a global promotion of all Alpha data.

| Provider | Intended role; no implicit operational authority |
| --- | --- |
| Alpha | Governed realtime universe baseline; specialist indicators separately |
| Yahoo | Existing five-minute discovery screeners, not universe coverage |
| Alpaca | Separate paper/execution rail; IEX/SIP feed according to account entitlement |
| Massive Basic | Entitled historical, end-of-day and reference uses; no snapshot entitlement |
| Financial Datasets | Corporate fundamentals and company evidence |
| Bigdata | Grounded research, filings, news and qualitative evidence |

## Inputs and volume

`alpha_market_baseline.plan` requires independent SHA-256 pins for an exactly
517-member unique universe and the explicit September 14 XNYS calendar. The
original symbol order is preserved, with no sorting, alias rewriting or omission.
Six batches have sizes 100/100/100/100/100/17. Their symbol hashes, slot numbers,
phase IDs, times and roots are bound into the plan and independently pinned
account evidence. Request parameters are function=REALTIME_BULK_QUOTES,
symbol=<exact comma-separated batch>, datatype=json. No undocumented entitlement
parameter is added to the bulk request. More than 100 symbols fails before I/O.
Official reference: https://www.alphavantage.co/documentation/#realtime-bulk-quotes
No documentation/demo provider request was made during implementation.

Three checkpoint anchors: opening 06:30:30, intraday 09:30:00, closing 13:00:30 PDT.
Each batch's earliest dispatch is anchor + 25 seconds * batch index, with a
five-second admission window and a 20-second total transport deadline. Thus
six batches finish within 150 seconds of each anchor if every gate passes.
A rolling minute contains at most three starts, far below 150/minute. Total:
ceil(517/100) * 3 = 18 requests, representing 1551 symbol observation opportunities,
not 1551 network requests. The MU qualification request remains separate.
Quotes are not an atomic exchange snapshot. Closing starts after regular close;
provider event times, rather than receive time, govern freshness claims.

## Ephemeral handling and integrity

EPHEMERAL_ALPHA_BULK is mandatory and exclusively allowed for this function.
Raw responses, prices, provider free text and hashes of provider data are not
published. Fixed classifications, grammar-validated symbols, provider timestamps,
missing/invalid field names, and coverage/freshness receipts survive. Unknown
or naive timestamp timezone is not invented. WITHIN_AGE_BOUND describes only
age evidence, not independently established realtime entitlement. Python memory
zeroization is not guaranteed. Response bodies are bounded to 1000000 bytes.

`qualify` serializes each daily slot with an owner-only descriptor-verified lock.
It publishes an exclusive immutable daily reservation before the existing
per-request reservation and dispatch. Slots cannot be repeated or skipped.
Every continuation supplies the independently expected previous completion hash;
all predecessor reservation, completion and sanitized receipt hashes must match.
The internal executor requires an explicit daily permit for bulk requests.
Missing or interrupted evidence fails closed. Reservations are never deleted or
released after interruption, partial coverage or ambiguous failure. No retries,
redirects, pagination, alternate accounts, feeds or providers exist in this path.
The executor does not create roots, schedule work, sleep or start services.

Missing/duplicate/unexpected/malformed coverage stops the daily chain after
sanitized diagnostics are persisted. A stale or timezone-unverified observation
is retained as such, never promoted to freshness GREEN. Missed windows fail
closed without backfill. Any later partial-session workflow requires a separately
reviewed plan; this day chain cannot skip the opening checkpoint.

## Monday execution gates

The reviewed Friday universe is not automatically fresh Monday membership.
Require a separately accepted exact universe and order, source checkpoint,
calendar and plan hashes, bulk-specific account entitlement and cost evidence,
new runtime closure including alpha_market_baseline.py, TLS and address pins,
all per-request manifest/account/runtime pins, output-root identity and one-attempt
reservations. Confirm the actual provider response schema and timestamp timezone
on the first authorized bulk response; fail closed on unknown schema rather than
use a different endpoint. No response-body retention is needed for this check.

The retained MU probe is scheduled only in its specification, not by a running
service: its unchanged window starts 06:30:30. The first bulk batch must wait for
MU success and still begin before 06:30:35. If MU/preflight/approval misses that
window, this proposed full-day plan fails closed. Do not backdate the opening or
pretend an after-opening start is full-session coverage. MU success does not
itself establish bulk entitlement or all-517 coverage.

All broker, paper-order, trade-execution, live-execution and ledger authorities
remain false. Installation and activation require a separate explicit authority.

## Successor readiness contract: pre-open bulk qualification

`alpha_session_readiness.readiness_plan` explicitly selects v2. The old v1 plan
and old MU qualification are historical independent contracts and are not the
Monday v2 activation plan. V2 has one ten-symbol REALTIME_BULK_QUOTES preflight
between 06:20 and 06:25 PDT and 18 collection calls, for 19 total. The pilot is
the approved MU/SPY/XLK/VNQ/TLT/GLD/UUP/IBIT/PFF/BIL list, which is not itself the
517-member stock universe. Ten-symbol reconciliation cannot prove all-517 access.

All six opening requests and responses must fall within 06:30:30–06:32:10 PDT;
intraday within 09:30:00–09:32:00; closing within 13:00:30–13:02:10. Slots within
a phase share its interval, preserving pinned order. Actual recorded dispatch
times enforce at most three starts per rolling minute, and clock rollback fails
closed. There is no promise that serialized requests at worst-case 20-second
latency can complete inside 100 seconds. Slow responses must fail the interval
gate; no silent extension or full-day GREEN. A controller may wait within the
explicit interval for a rate slot, but this library does not schedule work.

The preflight and all collection responses must have complete coverage and
WITHIN_AGE_BOUND timestamp evidence. Unknown timestamp timezone, stale data,
missing symbols or schema ambiguity stops continuation. Authentication and
account entitlement remain separate evidence gates; GLOBAL_QUOTE does not
supply the bulk preflight proof. Dispatch and response wall timestamps are
recorded for v2; provider timestamps remain in sanitized bulk_checks.

`final_session_receipt` joins independent, externally accepted stage receipts:
universe, preflight, opening, intraday, closing, Yahoo discovery, candidates/cases,
agents, committee, risk, paper decision. It verifies scope, session, stage,
expected hashes and predecessor links. Existing governance owners must verify
each stage's substantive evidence before accepting its independent hash. This
join does not run agents, examine ledgers, synthesize missing committee/risk
results or claim that a hash alone validates their semantics. Missing stages are
YELLOW; failed stages are RED. OFFLINE_TEST cannot become live GREEN. Explicit
broker_connected, paper_order_permission, trade_execution_permission and
live_execution fields are always false. A paper decision is evidence only, not
permission to submit a paper order.

The successor opt-in `alpha_session_runner` validates all nineteen independently
pinned admissions and the aggregate budget before dispatch. Its CLI is disabled
unless --run is explicitly supplied to a live package. The enabled path checks
the date, waits only inside the explicit plan, enforces rate slots, stops after
any failed attempt and supports cooperative SIGTERM/SIGINT shutdown. There are
no retries or providers outside Alpha. Missing Yahoo/agent/governance stage
receipts remain YELLOW, even after successful Alpha collection. Existing agents
and services are not activated by this runner.

The disabled installation rehearsal publishes only a disabled plist inside a
new independently pinned artifact root. It never registers launchd, invokes
launchctl, starts a service or includes --run. This is not native startup or
production installation acceptance. Production package, account and source
checkpoint pins must be released separately; source preparation does not make
actual bulk schema/timezone verification or full-session governance evidence true.
