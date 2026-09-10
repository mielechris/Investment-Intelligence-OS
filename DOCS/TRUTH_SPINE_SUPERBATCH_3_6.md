# Superbatch 3.6 — source-only full-session observer

Base: `a3215517fe8245e1384326f5a91a953eceaf2feb`. This checkpoint implements
and tests a future **deny-only observer**, not a full-day installation or run.
Permanent production remains YELLOW. No permission to bind 5291, start a
full-day shadow, load a LaunchAgent, spend, trade, or promote follows from this
document or its template. Retained Superbatch 3.5C evidence is not rewritten.

## Calendar, clock and authority

`truth_spine_session.py` implements PREMARKET_PREPARATION, PREMARKET_READY,
OPENING_OBSERVATION, REGULAR_SESSION, CLOSING_OBSERVATION,
POST_CLOSE_RECONCILIATION, SESSION_COMPLETE, SHUTDOWN_COMPLETE and FAILED_CLOSED.
The reviewed calendar is bounded to XNYS 2026, with explicit holiday and
short-session tables from the [NYSE calendar](https://www.nyse.com/trade/hours-calendars).
Other years are rejected, not guessed. Exchange times use America/New_York;
Pacific display uses America/Los_Angeles. UTC-aware timestamps are persisted.
DST, weekends, holidays and short sessions are tested independently of host TZ.

Normal opening/closing is 06:30/13:00 Pacific daylight time; short sessions close
10:00 Pacific. Preparation begins 90 minutes before opening. Premarket-ready
begins 15 minutes before opening. Opening observation lasts 30 minutes; closing
observation starts five minutes before close. Post-close reconciliation has
15 minutes, followed by at most five minutes for shutdown. Authority is issued
before startup, binds exactly one calendar/session, and never exceeds 24 hours.
The runner requires an independently approved SHA-256 of topology bytes; that
topology pins the deny-only authority content hash. Resealing an edited authority
does not renew permission. Renewal requires new owner authorization and binding.

All ten capabilities remain false, including provider, model, credential,
paper-order, broker, execution, operational-ledger-write, promotion and operational
scheduler/publisher authority. Shadow-local capture/publication does not grant
operational publication. Production CLI accepts no clock override. Tests inject
time directly into isolated objects. A monotonic runner deadline prevents a
backwards wall-clock jump extending the approved session. Late startup and missed
phases are disclosed; no historical refresh is manufactured to fill a gap.

## Immutable captures and canonical journal

`truth_spine_generations.py` consumes an independently pinned source registry:
exactly one L7 operational ledger, one L8 historical ledger, and explicitly
listed supported retained stores. A permanent source-cycle manifest may be
retained as historical input, but is not the shadow observation-cycle receipt.
No source discovery, credentials or browser-supplied paths are accepted.

Each refresh writes a unique `captures/capture-<uuid>/` with SQLite read-only
backup-API snapshots and fixed retained-file copies. Every source binds its
logical store, registry/path hash, capture start/end, schema, integrity result,
bytes, SHA-256, record watermark, original clocks and evidence classifications.
L7 and L8 are consistent independently, **not globally simultaneous**.
Capture manifests are hash-chained. Selection and canonical event admission
commit in one FULL-synchronous SQLite transaction. Event identity uses logical
source store plus original object ID, not capture-file hash. Changed content
under an existing identity aborts admission. Prior generations and abandoned
unselected captures are retained. No in-place repair or snapshot reuse exists.

Refresh cadence is 900 seconds in preparation/ready/regular phases and 300
seconds during opening/closing/post-close. This bounds database copying while
showing faster transition evidence. The parent checks lifecycle/children every
five seconds, not every-source copying every five seconds. A failed capture
retains the prior selected bytes but marks them STALE and fails readiness.
Validation reconstructs event provenance from snapshots, checks schema/integrity,
and verifies the journal hash chain. Immutable-input hash caching is invalidated
by device, inode, size, mtime, ctime or expected hash changes.

## Real service, projection and readiness paths

`truth_spine_full_day_service.py` is the fixed future child module. The parent
owns capture and scheduling; the scheduler child attests to that persisted
schedule; the publisher derives its projection from the selected capture and
lifecycle journal. No harness assigns a projection generation to make it pass.
`RuntimeProbeReader` reads package/runtime/frontend inventories, stabilized OS
fingerprints, startup-receipt-bound heartbeats, the real publisher file and the
independently committed capture-owner source-cycle receipt. All probes bind session, release, generation and
watermark; backend reads cannot trigger capture, renewal, repair or publication.

- `/health/live`: process availability only.
- `/health/ready`: 200 only with all required current bindings; otherwise 503.
- `/health/market-readiness`: always 503 in this deny-only observer.
- `/health/research-readiness`: SHADOW_OBSERVATION_READY, not live research.
- `/truth-spine/full-session`: sanitized current/stale/failed metadata; no controls.

Heartbeats/projection expire after 30 seconds; derived probes after 15 seconds.
Shadow source-cycle publication AND capture completion must be at most 900 seconds old.
A fresh HTTP wrapper cannot renew either nested timestamp. Historical
case timestamps remain historical; they are exposed separately from capture
freshness and do not become new market observations. Missing dependencies are
not replaced by literal readiness flags.

Publisher lag after capture selection is expected to produce temporary 503.
Post-close waits for a genuinely reconciled publisher inside its fixed window;
subsequent stale readiness revokes that reconciliation. Missing reconciliation
at the deadline fails closed. It never extends the deadline to obtain success.

## Supervision, checkpoints and cleanup

`truth_spine_full_day_runner.py` reuses the reviewed OwnedChildren fingerprint
acquisition and reverse shutdown checks. Only the service module allowlist was
extended; PID/start/PPID/argv/cwd/executable/startup-receipt checks are unchanged.
One backend, scheduler and publisher are allowed. Each role has one restart,
three total, with 60-second cooldown reserved in the journal **before** launch.
Restart cannot reset the budget or duplicate canonical event IDs. Expiry stops
new work, but never cancels verified cleanup authority. An unverified child is
never signaled; cleanup continues for the other verified children and reports RED.

A crashed parent's surviving children are not adopted. Runner/child locks must
all be free before a subsequent runner starts. If children survive, independent
owner-reviewed cleanup is required; automatic safe adoption is not claimed.
Logs are capped at 1 MiB each. Disk preflight reserves 110 captures at twice the
current source size plus 64 MiB for journal growth; concurrent disk consumption
can still fail a later write, which triggers safe cleanup. No permanent paths
are written as a fallback.

Append-only checkpoints cover startup, premarket-ready, open, 15-minute regular
intervals, before close, close, post-close reconciliation and shutdown. They bind
session/phase, selected capture, canonical watermark, actual verified projection
hash/generation (or null), child fingerprints, authority hash/lifetime, readiness,
incidents and observer-scoped zero activity counters. They do not claim retained
operational history has zero credits. Shutdown retains the journal, original
startup receipts, runner incident report, acceptance report and sealed shutdown
receipt. Failure to persist diagnostics is itself RED, never fabricated success.

## Browser contract

The existing preview's `?fullSession=1` selects a same-origin read-only metadata
endpoint; it does not infer evidence provenance or grant authority. One bounded
poll owner is canceled on unmount. The view displays phase, capture status,
generation, source cycle, watermark, source-qualified records and original
clocks/classifications, separate universe identities/counts, owners, all false
capabilities, observer counters and incidents. SESSION_CLOSED and INSTALLED_DISABLED
remain different concepts. MAX/dialogue is NARRATIVE only; Day Trading ABSTAINED.
Unknown schema, malformed labels, stale wrapper, nonzero observer counters or
any authority violation fails closed. Layout uses normal flow, wrapping and
responsive minmax columns. Source tests are not a Safari-rendered full-day claim.

## Future package allowlist and procedure — NOT executed here

`config/truth-spine-full-day-shadow.json.template` is uninstalled and contains
placeholders, not an executable authorization. Proposed port is **127.0.0.1:5291**;
future preflight must recheck its absence and the full protected port/PID map.
Root must be a new explicitly authorized `/private/tmp/iios-truth-spine-full-day-<session>`.
No LaunchAgent is produced. The fixed backend allowlist is `BACKEND_FILES` in
`truth_spine_session_package.py`: eleven named Truth Spine modules plus the two
reviewed runner scripts, copied to `release/backend/`. No legacy application,
provider implementation or mixed checkout belongs in that directory.

1. Obtain separate owner approval for date/calendar, root, duration and port.
2. Verify clean synchronized source, retained-input pins, runtime and permanent
   baseline. Build frontend twice using the committed reproducibility procedure;
   require identical input/output inventories and six-file provenance-valid output.
3. Under the separately approved root create only the template's directories and
   files. Copy fixed source files, six frontend files and the completely verified
   runtime. Bind exact bytes/modes in `iios-full-day-shadow-package-v1`, including
   clean source commit, session, registry, authority, runtime and frontend pins.
   Package directories are owner-only; data 0600, code 0400, executables 0500.
4. Use the pure `deployment_documents` constructor; it performs no installation.
   Independently approve the resulting topology-byte hash. No manual field repair.
5. Verify package file graph, nested runtime inventory, inherited platform hashes,
   selector/session/calendar binding, source ownership, available disk, empty locks
   and free port. Retain pre-copy manifests and read-only input baselines.
6. Only under the later execution authorization invoke the package-local Python
   and runner with `--root`, `--owner-topology-sha256`, `--owner-session-identity`.
   The source checkout runner rejects execution as a mixed runtime.
7. Review `/review/truth-integration.html?fullSession=1` at desktop/medium/narrow,
   monitor checkpoints, and verify final reverse cleanup and port clearance.
8. Rehearse rollback using a consistent journal backup and immutable captures in
   another explicitly authorized isolated copy. Never overwrite the original.
   On failure retain the entire root; do not touch permanent services or snapshots.

## Validation boundary

Offline tests use temporary SQLite stores, a compressed clock and fake OS child
boundaries, while exercising real capture, publisher, readiness and browser
handlers. Tests cover normal/short/holiday/DST sessions, late start, clock jumps,
stale source/publisher, post-close lag/failure, dead children, restart limits,
authority expiry, persistence failure, hashes, schema, identity mutation and
rollback-copy preservation. The independent frontend-build test uses a disposable
committed snapshot of candidate source with byte-verified locked dependencies;
production clean-source/provenance rejection remains unchanged.

Source/simulation GREEN permits a source checkpoint only. Actual full-day runtime,
long-duration disk/RSS behavior, live host sleep/wake and Safari interaction remain
acceptance gates of a **separately authorized** rehearsal. Permanent promotion is
not authorized by source test results.

## Superbatch 3.6A — independent shadow observation cycle

The permanent projection manifest was stale, correctly rejected by the original
900-second gate. It must never be retimestamped, recopied as fresh market truth,
or used as the shadow's own observation clock. The replacement measures a NEW
read-only observation of existing stores, not new provider or market activity.
Permanent inputs and all original evidence classifications/clocks stay unchanged.

The capture/scheduler owner, not the projection publisher, appends one
`iios-shadow-capture-source-cycle-v1` receipt to `session-journal.db:source_cycles`
AFTER the read-only snapshot integrity/admission transaction commits. The table
has unique capture/sequence keys and update/delete denial triggers; it is in the
0700 isolated root, in the 0600 FULL-synchronous journal. Receipt commit and
directory fsync complete before capture is marked CURRENT. No previous row is
overwritten. Production publisher/backend open the journal read-only and cannot
call the issuance path. The topology independently binds distinct capture/scheduler
and publisher owner identities; receipts must match those exact owners and roles.
These hashes are integrity/ownership bindings within the reviewed owner-only
runtime, not cryptographic signatures against arbitrary malicious same-UID code.

The complete receipt binds schema/version, sequence and previous receipt hash,
session, phase, capture ID/hash, individual L7/L8 snapshot identities, source
aliases/path bindings, database hashes, schema/integrity checks, per-store
watermarks, admitted cumulative event watermark, original evidence clocks and
classifications, capture start/end, publication time, topology/authority hashes,
producer/consumer identities, and explicit non-global-simultaneity disclosure.
`source_cycle_id` is SHA-256 of canonical sorted ASCII JSON with compact separators,
`ensure_ascii=True`, `allow_nan=False`, and one trailing LF, excluding ONLY the
`source_cycle_id` field. No additional mutable content-hash field is excluded.
The first parent is the session/registry journal binding; later parents are exact
prior source-cycle identities. Validation reconstructs each cumulative watermark
from immutable snapshots, not a caller-supplied ready flag.

Capture completion to receipt publication is bounded to 0–30 seconds. A restart
after admission but before publication may finish only that recent pending
receipt. Older pending captures fail closed; they cannot acquire a fresh clock.
Repeated processing returns the exact existing receipt without writing. A gap,
fork, changed ancestor, wrong session/phase/owner/topology/authority, snapshot or
watermark mismatch is rejected. Consumers verify the complete chain and selected
generation. Freshness requires both receipt age and capture-end age in [0,900]
seconds. Touching, copying or reserializing old bytes never changes these clocks.
Capture rejects reversed time or wall/monotonic elapsed disagreement over five
seconds; the existing lifecycle handles between-cycle discontinuities.

Post-close ordering is capture → integrity/admission commit → independent receipt
commit → CURRENT lifecycle → independent publisher verification/projection →
readiness/source-cycle/watermark equality → reconciliation → SESSION_COMPLETE →
shutdown. Receipt/publication gaps return 503 and never self-issue upstream data.
Expected publisher lag is bounded by the existing reconciliation deadline, not
repaired with fabricated projections or renewed authority. Failed capture leaves
the old receipt untouched and capture STALE. HTTP readiness revalidates the nested
receipt even if the outer probe wrapper is still fresh.

The authoritative future review URL, including generated templates/reports, is:
`http://127.0.0.1:5291/review/truth-integration.html?fullSession=1`.
It selects `/truth-spine/full-session`. Omitting the query continues to select the
historical `/truth-spine/museum` API; no silent full-session fallback or alias is
introduced. The full-day service does not serve that historical API.

No full-day root, port binding, installation or permanent service change is
authorized by this source-only correction. A new dated full-day authorization
must bind the new source candidate, fresh builds, exact package and runtime pins.

## Superbatch 3.6B — governed full-factory coverage

The existing publisher now includes a sealed `iios-full-factory-shadow-coverage-v1`
extension in the full-day projection. Readiness independently reconstructs it from
the selected, hash-validated capture and its authenticated source-cycle receipt.
The browser reads that exact publisher artifact; it cannot construct an alternative
ready inventory. Missing, mismatched, stale or tampered projections yield readiness
503 and unavailable coverage. A current browser response timestamp cannot refresh
the original capture, event, observation or publication times.

The 24 stable product IDs/names/classifications/routes are pinned to the committed
product registry. Eight specialist IDs/names/roles are pinned to `AGENT_CONFIGS` by
AST comparison, without importing the application or contacting a model. Skeptic
is also an explicit governance view of the registered `skeptic` agent, not a ninth
specialist. Committee and deterministic Risk use their own typed ledger records.
Frontend catalog equality is tested against these same source definitions.

Only explicit `product_id`/`room_id` or `agent_key`/`agent_id` references qualify a
record for an individual room or specialist. Conflicting aliases fail closed.
Ticker, family, aggregate counts and general case totals never assign activity.
Unregistered references do not bind any registered object. Completed specialist
results require explicit `status=complete` and remain retained, source-qualified
results, not new invocations. Each card binds its session/generation/source cycle,
classified record identities, original payload hashes and clocks. Disclosures show
at most 20 references, with exact full-set count and canonical hash. They do not
change the underlying complete immutable captured records.

Configuration identity is distinct from evidence availability and current activity.
Unbound counts remain null/UNAVAILABLE; captured HISTORICAL, REPLAY, SIMULATED,
NARRATIVE, UNAVAILABLE and other approved classifications remain unchanged.
Rooms are observation-only and specialists suppressed by this deny-only session.
No configured room is labeled live merely because an observer is running.
Subsystem source summaries do not infer health or execution of permanent services.

Bigdata, Financial Datasets, Alpha Vantage, Alpaca market data, Alpaca paper,
OpenAI, Gemini, Grok, MCP and Vercel each have separate disabled cards. No approved
precomputed configuration/credential record is currently bound to these captures;
configured and credential presence therefore remain UNKNOWN. The view explicitly
does not probe the environment, secret selectors, Keychain, network, provider,
model or MCP. Zero requests describe only this deny-only observer, not historical
host activity. Costs are unavailable without governed accounting. Vercel is
presentation infrastructure, never an authoritative evidence source.

Day Trading remains OBSERVATION_ONLY with zero order allowance, no broker
connection, paper/live authority false and visible fail-closed lock. NAV/cash/
positions may come only from the latest uniquely dated L7 paper snapshot and are
labeled retained, not current account truth. Missing or tied snapshots are null.
No opportunities, performance, paper orders or account values are synthesized.

History summaries retain separate L7/L8 store namespaces and original hashes.
Opportunity candidates join the existing read-only typed ledger allowlist.
Pattern, professional-judgment and price-archive source kinds may be explicitly
registered through the same pinned document reader; no new paths are discovered
or captured automatically. Without such inputs their individual panels remain
UNAVAILABLE. The 517/518 universe capture identities remain separate, with no
inferred per-product membership. Original private content never crosses the
metadata boundary.

The existing full-session route/poll owner is unchanged. Normal-flow disclosures
cover rooms, specialists/governance, routing, subsystems, history, locked Day
Trading, source freshness and the phase contract. The timeline is not a claim
that every listed phase occurred. Permanent production stays explicitly YELLOW
and unassessed by the shadow. Responsive wrapping uses the existing bounded grid
and single-column narrow breakpoint; required sections are not hidden by width.

The full-day immutable backend graph adds only `truth_spine_factory_coverage.py`.
The new generation event metadata changes capture identities; this source update
is for a new separately authorized root and must not be applied over retained
rehearsal evidence. Offline tests cover actual publisher/GET reconstruction,
source preservation, restart determinism, tampering, unavailable information,
classification preservation, locked authority and configuration catalog equality.
Source/static acceptance is not actual Safari/full-day runtime acceptance.
No full-day root, runtime, LaunchAgent, installation or port binding is authorized
by this implementation. A new dated authorization must pin the new commit, package
and independently reproduced frontend provenance before any actual rehearsal.
