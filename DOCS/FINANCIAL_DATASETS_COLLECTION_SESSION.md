# Explicit-session collection readiness

This source revision replaces the collector's implicit September 11 session with
a required `--session-date YYYY-MM-DD` on every CLI command. It grants no account,
credit, installation or execution authority. Earlier source, runtime, dashboard
and browser evidence retain their original identities.

## Calendar and schedule

`SessionPlan` admits regular XNYS cash-equity sessions in the bounded published
2026 calendar. Weekends, the ten published exchange holidays, malformed dates,
out-of-range dates and unsupported previous-session lookups fail closed. The two
early-close dates require a separately reviewed schedule and are rejected.
Timezone-aware session times handle daylight-saving offsets; fixed UTC offsets
are not used for new dates.

Sources:
- https://www.nyse.com/publicdocs/nyse/ICE_NYSE_2026_Yearly_Trading_Calendar.pdf
  (preserved PDF SHA-256 `70f5577eb43e60a9dbbecaae3cec23d0f02028c05c7f175013bb3e97816d394f`)
- https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-Closings-Calendar/

This is a versioned published calendar, not a live exceptional-closure service.
Before arming, the owner must independently verify the session remains open,
pin that dated calendar evidence, and supply current account evidence through
expiry. A new calendar year or exceptional closure requires review; the program
does not infer availability from weekdays or a provider response.

For Monday September 14, 2026, the previous session is Friday September 11.
The ten tickers, in order, are MU, SPY, XLK, VNQ, TLT, GLD, UUP, IBIT, PFF, BIL.
Each phase contains ten requests spaced six seconds apart:

| Phase | First target PDT | Dispatch deadline PDT | Requests |
|---|---|---|---|
| Opening snapshots | 06:30 | 07:00 | 10 snapshots |
| Point-in-time OHLCV | 06:32 | 09:30 | 10 daily prices, September 11–14 |
| Facts/prior baseline | 06:34 | 09:30 | MU facts; 9 daily prices, September 11 |
| Intraday snapshots | 09:30 | 12:55 | 10 snapshots |
| Closing-window snapshots | 13:00 | 13:05 | 10 snapshots |

There are 50 rows: 30 `/prices/snapshot`, 19 `/prices`, 1 `/company/facts`.
One credit per row is a required account-evidence condition, not an inference
from public prices. Authority expires Monday at 20:05 UTC / 13:05 PDT.
Closing-window snapshots do not prove an official exchange closing auction.
Historical daily observations remain explicitly historical.

## Binding and migration

The explicit plan passes through release admission, journal, account, authority,
transport and supervision. No production session-date default exists. The v2
specification hash binds the calendar source, date, previous session, exact row
hashes, selector and limits. Release schema `fd-collection-release-v2` binds that
specification, installed root, source inventory and interpreter. V1 manifests
cannot be relabelled. Old account/authority dates, old selector, wrong plan,
wrong release and wrong interpreter fail closed.

Only this collection path uses Keychain service
`IIOS_FINANCIAL_DATASETS_API_KEY`, account `iios-provider`. The secure adapter is
constructed lazily after verified release and account/authority gates. There is
no selector fallback. Credential values are never logged, persisted or hashed.
Unrelated legacy provider APIs retain their behavior and confer no collection
authority.

The Friday exact-row fixture remains a regression test. New Monday tests verify
all 50 rows, holidays/DST, migration rejection, no 51st reservation, failed
request no-retry, missed-opening classification and cooperative shutdown.
Native tests use disposable roots, synthetic account evidence, an injected
clock and a local fake TLS provider. The production CLI has no clock override.

## Installation gates and rollback

Before generating a fresh release, independently pin the accepted implementation
commit and complete byte inventory. Requalify the existing sealed runtime bytes
against that source; never rewrite its earlier qualification receipt. Bind the
native verified launcher, actual interpreter, complete runtime inventory, TLS
bundle and actual installed root. Preserve owner/non-group-writable checks.

Require current authoritative entitlement, ten-ticker coverage, per-request
unit cost, at least 50 available unreserved units, a separately approved exact
50-unit reservation, rate >=10/minute, internal-use rights, overage/top-up policy,
ambiguous billing treatment and non-secret account-to-selector binding. Missing
or conflicting evidence fails closed. Dashboard dollar balances and historic
successes cannot stand in for units or entitlements.

Generate a new disabled release and review its manifest and LaunchAgent plist
before any installation authorization. Plist label includes the explicit date;
its arguments include date, source, root, release, account and authority pins.
No listener is required by the production collection supervisor. `KeepAlive`
remains false. Same-day owner approval must be within a <=30-minute arming
window ending no later than 06:30 local market-session time. Installation,
verification and arming must finish before that time for full-session eligibility.

An already armed collector that misses observations records MISSED and partial
coverage; it never backfills opening data. New arming after the deadline fails
closed. All reservations are durable before dispatch, including ambiguous
requests. There are zero automatic retries, no replacement reservations and no
51st request. Provider failure is terminal and retained.

Rollback uses the exact-root disarm operation and cooperative shutdown. Before
any signal or service removal, independently verify the owned process's PID,
PPID, start time, command, cwd, executable bytes and release-root identity.
Never kill by name or resume an old session. Preserve all receipts and raw
evidence. Do not delete an interrupted root or release ambiguous credits.
An identity mismatch requires owner review, not force cleanup. Permanent
unrelated services, ledgers, brokers, orders and Northstar/WebKit are out of scope.
