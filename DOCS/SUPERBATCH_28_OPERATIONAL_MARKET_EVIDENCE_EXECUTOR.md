# Operational Market Evidence Executor

This source-only checkpoint adds a disabled-by-default, restart-safe coordinator between the immutable one-day policy and the already reviewed Financial Datasets credential and verified-TLS boundaries. It performs no Keychain or network access merely by importing, validating, or starting the existing disabled supervisor.

The full immutable plan contains 50 one-credit identities: ten opening snapshots, ten prior-session OHLCV observations, ten intraday snapshots, one MU company-facts observation, nine fund/ETF baselines, and ten closing snapshots. `PARTIAL_SESSION_LATE_START` is a separate deterministic plan. It never creates opening identities after the opening window and includes only still-available windows; its plan hash and exact maximum cost are computed from the resulting immutable rows.

Every request is durably recorded as `PLANNED`, `RESERVED`, and `DISPATCH_STARTED` before transmission. It then becomes `CONFIRMED`, `AMBIGUOUS`, or `FAILED_PRETRANSMISSION`. Confirmed and ambiguous identities can never be sent again. A process recovered with `DISPATCH_STARTED` classifies that identity ambiguous and charges it once. Only a proven pre-transmission failure remains unspent, and automatic retry is prohibited.

Raw licensed responses and receipts use separate owner-only directories. Writes use atomic replacement, file fsync, and directory fsync. Browser projection contains only lifecycle counts, credit counts, phase, next gate, plan classification, stages, and false authority fields. It contains neither provider bodies nor request identities.

The fixed installer binds a source commit, artifact hashes, coordinator identity, fixed owner-only state/evidence/receipt/recovery roots, the Financial Datasets selector, host, and endpoint allowlist. Installation creates only the immutable `SPY_SNAPSHOT_CANARY_1` plan and leaves network access disabled. The full-session and late-session plans remain unauthorized. Supervisor startup reconstructs and recovers the installed coordinator, but only the explicit owner-only canary command can dispatch the canary; browser invocation is rejected.

The canary records `RESERVED` and `DISPATCH_STARTED` before transport, permits one Keychain retrieval and one `/prices/snapshot?ticker=SPY` transmission, and never retries. A transmitted response that fails an HTTP, content-type, size, ticker, timestamp, or schema gate is conservatively terminal and ambiguous. Every success or failure path returns released allowance to zero and locks all stages.

The authenticated compositor reads only the fixed installation and state roots. Browser states are `NOT_INSTALLED`, `INSTALLED_DISABLED`, `CANARY_READY`, `CANARY_RUNNING`, `CANARY_CONFIRMED`, `FAILED_CLOSED`, and `UNAVAILABLE`; it projects counts and authority locks, never request identities, provider bodies, or credential material. The fixed provider contract is `api.financialdatasets.ai:443`, `X-API-KEY`, the dedicated Financial Datasets Keychain selector, and only `/prices/snapshot`, `/prices`, and `/company/facts`. No secret is stored, logged, hashed, projected, or passed outside the header boundary.

The first operational authorization after this checkpoint is restricted to one SPY `/prices/snapshot` canary and at most one credit. The daily plan must not be authorized until that canary creates a validated persistent receipt visible through the authenticated Museum projection.

After a confirmed intraday SPY canary, the separately authorized `POST_0930_PARTIAL_SESSION` transition may create exactly twenty rows: ten intraday and ten closing snapshots. It excludes opening evidence, baselines, and company facts. The transition validates the original receipt and evidence hashes, provider, symbol, endpoint, session date, intraday timestamp, schema, and one-credit accounting before adopting that receipt as the SPY intraday row. The original identity and files remain immutable; a hash-valid adoption link records the relationship, and SPY is never retransmitted. The remaining allowance is exactly nineteen credits. Closing rows run only from 12:55 through 13:05 PDT and terminal closure returns allowance to zero.

## September 9 readiness

`SEPTEMBER_9_MARKET_OPEN_50` is a separately constructed, immutable plan. Its fifty identities include the September 9 session date and are disjoint from every September 8 identity. The plan contains ten opening snapshots (06:30–07:00 PDT), twenty baseline observations (06:30–09:30 PDT), ten intraday snapshots (09:30–12:55 PDT), and ten closing snapshots (12:55–13:05 PDT). Its exact and maximum credit requirement is fifty; automatic retries remain prohibited.

The non-spending administrative validator accepts only explicitly reviewed Financial Datasets pricing metadata whose observation is UTC-aware, no more than twenty-four hours old, and remains valid through 13:05 PDT on September 9. It constructs and validates metadata in memory only: it performs no provider request, credential access, installation, allowance release, or operational-state mutation. A separate owner authorization and rollback-backed installation are required after the September 8 session reaches its locked terminal state.

The session-generation transition is also inert until separately invoked. It requires the September 8 `POST_0930_PARTIAL_SESSION` to be closed, fully terminal, zero-allowance, and locked. It copies the plan, state, last-known-valid state, adoption link, receipts, and evidence into an owner-only `2026-09-08` archive and binds every regular file's path, size, and SHA-256 in `iios-operational-market-session-archive-v1`. The original state root is never moved, rewritten, or deleted. A new locked `2026-09-09` generation is built separately, and an fsynced `iios-operational-market-session-selector-v1` pointer is the sole atomic selection boundary. Missing selectors retain September 8; malformed, stale, mixed-session, or hash-invalid selectors fail closed. The supervisor constructs its coordinator only from the installer-validated selected root.

## Legacy supervisor layout migration

The supervisor installer explicitly recognizes the deployed five-artifact predecessor only when its `iios-unattended-supervisor-installation-v1` manifest, source commit, five hashes, canonical inventory identity, LaunchAgent bytes, owner, `0700` directories, and `0600` regular files all validate. Unknown, incomplete, mixed, symlinked, special-file, permission-invalid, or hash-invalid layouts fail closed. The reviewed target is the same manifest contract with eight fixed artifacts: the four legacy Python modules, the operational executor, executor installer, executor service, and the unchanged LaunchAgent plist.

Migration is a stopped-service transaction. Before teardown, operations must call `create_legacy_migration_backup` and `rehearse_legacy_restoration` against fixed owner-only destinations. The rollback package contains the byte-exact legacy artifact tree, installation manifest, and LaunchAgent plus an immutable `iios-unattended-supervisor-layout-rollback-v1` inventory binding every relative path, size, mode, and SHA-256. It is never rewritten or deleted. After the exact launchd label, PID, supervisor lock, and absence of listeners/children are proven clear, `migrate_legacy_layout(..., service_stopped=True)` builds the eight artifacts in a sibling staging directory, validates them, writes an fsynced phase journal, and selects the staged artifact directory with an atomic rename. The manifest and unchanged plist are then atomically replaced and the complete target is revalidated. A failure after selection restores the legacy root from the retained package; an interrupted invocation either safely resumes from validated legacy state or recognizes and completes an already-valid target.

The protected September 8 operational state root is hashed before and after the transaction and must remain byte-identical. This layout migration never archives, creates, or selects a market-session generation; releases no allowance; and grants no provider, promotion, paper-order, broker, ledger-write, or live-execution authority. The reviewed operational sequence is: validate candidate and legacy installation; create and rehearse rollback; boot out only the unattended supervisor; prove the teardown barrier; invoke the migration once; bootstrap once; verify one launchd-owned supervisor, one lock, no children/listeners, zero released allowance, locked stages, and byte-identical September 8 state; otherwise restore once from the retained legacy package. Generation selection remains a separate authorization.

## September 9 pricing-evidence administration

`SEPTEMBER_9_MARKET_OPEN_50` is reconstructed from fifty source-controlled, date-bound request rows and canonical ASCII JSON. Independent reconstruction yields plan identity `d08262228104ee464d602688aae6e1c97e67db10e640233deff87a1231e63c23`; the previously supplied `c40b4c24…` value has no committed serializer, fixture, or Git-history provenance and is rejected. The plan is not modified to reproduce an external identity.

The fixed non-spending administrator accepts only `iios-provider-endpoint-cost-contract-september-9-v1`, the fixed Financial Datasets public pricing URL, the reviewed snapshot/historical/company-facts endpoint identities, fifty unique identities, one credit per request, exact and maximum cost `50/50`, zero retries, and the canonical plan identity. Observation and expiration must be UTC-aware, current, no more than twenty-four hours apart, and cover `2026-09-09T20:05:00Z`. It accepts no account, API, credential, market-data, browser, provider-execution, allowance, or generation-selection input.

Before replacement, the administrator authenticates the exact installed September 8 cost document even when its freshness has expired. It atomically creates an owner-only rollback directory containing the byte-exact predecessor and a hash-bound immutable receipt, writes the September 9 candidate as a sibling `0600` staging file, fsyncs and validates it, and atomically selects it. Restart finds either the authenticated predecessor or the fully authenticated successor; leftover owned staging is safely reconstructed. A post-selection failure restores the predecessor byte-for-byte. The operational reader accepts either exact schema but binds September 9 only to its date and canonical plan. Refresh never reads Keychain, contacts the provider, releases credits, changes a generation selector, or enables trading authority.
# September 9 canonical-plan recovery

The corrected September 9 contract uses one canonical row structure and one
canonical identity in readiness, execution, installation, selection,
supervision, and browser projection. Neither the former readiness identity
`d08262228104ee464d602688aae6e1c97e67db10e640233deff87a1231e63c23`
nor the incident executor identity
`c40b4c241d114df4d95069e55e7c68a4fbc8e1c899c5faa6aa8e3767b97a626a`
is accepted for corrected execution.

The plan contains 50 one-credit, zero-retry rows. Opening snapshots run from
06:30–07:00 PDT, all point-in-time OHLCV, prior-session baseline, and MU facts
rows run from 06:30–09:30 PDT, intraday snapshots run from 09:30–12:55 PDT,
and closing snapshots run from 12:55–13:05 PDT. Point-in-time OHLCV transmits
`start_date=2026-09-08&end_date=2026-09-09`; the nine prior-session baselines
transmit `start_date=2026-09-08&end_date=2026-09-08`. MU company facts carries
no historical date range.

The old `d082…` pricing document is retained byte-for-byte but is ineligible
for the corrected plan. A fresh public-documentation observation is installed
only through `--refresh-corrected-september-9-cost-contract`, with its own
owner-only rollback package. This path has no provider, account, credential,
credit, allowance, generation, or trading capability.

The selected `c40…` generation may be superseded only when it has zero
allowance, all stages locked, all rows still PLANNED, zero dispatches, zero
receipts/evidence, zero credits, and zero Keychain accesses. Recovery writes a
hash-bound inventory receipt, constructs a distinct
`sessions/2026-09-09-canonical-v2` generation, validates corrected pricing,
and atomically replaces the selector. The selector binds the September 8
archive hash, supersession-receipt hash, and corrected canonical plan identity.
Post-selection failure restores the original selector bytes; neither the
incident generation nor the September 8 archive is rewritten or deleted.

### Owner-only September 9 authorization

`--authorize-september-9-market-open-50 --owner-authorized --authorized-commit <exact-commit>` is the sole administrative release boundary. It validates the corrected selector, pricing, archive, supersession receipt, installed manifests, pristine generation, and authorization clock; writes byte-exact pre-authorization state backups and a hash-bound receipt; then releases exactly 50 credits without dispatch. Window enforcement remains exclusively in the supervisor. Repetition is idempotent; browser invocation, late authorization, prior activity, and inconsistent state fail closed.

## Overnight bounded-wait recovery

An owner-authorized future session is classified from `America/Los_Angeles`
civil time as `PRE_SESSION_BOUNDED_WAIT`, `ACTIVE_SESSION_DATE`,
`POST_SESSION_EXPIRED`, or `INVALID_SESSION_TIME`. The wait begins at the
recorded authorization on the immediately preceding local date. It performs no
dispatch or credential retrieval before the 06:30 opening boundary. Midnight,
restart, and repeated supervisor ticks preserve that wait; 06:30 transitions
to active-window processing. Past sessions, times before authorization,
unbounded prior dates, malformed timestamps, and expired sessions fail closed.
Missed windows are never caught up.

The recovery never edits or reopens the generation failed solely with
`SESSION_TIME_INVALID`. It binds that generation's complete inventory, its
authorization receipt, zero operational activity, and failure category in an
immutable supersession receipt. It creates the collision-free
`2026-09-09-canonical-v3` successor from the same canonical plan with zero
allowance and every stage locked. The atomic selector binds the September 8
archive, the c40 incident receipt, and the time-failure receipt; a failed
post-selection validation restores the previous selector. Reauthorization is
a separate owner-only operation. Recovery itself never releases credits or
contacts the provider.
## Superbatch 31 provider endpoint certification

The historical-prices contract is `GET /prices` with `ticker`, `interval=day`,
`start_date`, and `end_date`. Historical success is the documented `prices`
array with daily `time` values and numeric OHLCV fields. Company facts uses
`GET /company/facts?ticker=MU` and the documented `company_facts` object.

Provider errors are classified using sanitized status, media type, byte count,
envelope class, and the exact rejecting predicate. Raw error bodies and private
headers are never retained. A separate owner-only certification store contains
three immutable one-shot MU identities: September 8–9 point-in-time OHLCV,
September 8 prior-session OHLCV, and company facts. It has a three-credit hard
limit, stops on the first failure or ambiguity, never retries, and always returns
released allowance to zero. It does not share state, identities, evidence,
receipts, or accounting with a market-session generation or the paper fund.
