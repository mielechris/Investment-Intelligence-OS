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

## Superbatch 3.6C — Northstar full-session presentation (source candidate)

This candidate keeps the accepted Auction Edition / Museum Master 1.2 shell,
seven destinations, architectural factory floor, MAX, canonical character art,
room-dialog geometry and keyboard interaction model. It adds a separate named
full-session shell rather than mounting the engineering preview or its payload.
The normal permanent entry remains `main.tsx` and the normal snapshot owner.
Named isolated exports in the existing shell, Control Room, Case Library and
Expansion Wing select governed session destinations. The isolated room-dialog
export retains the accepted geometry while replacing legacy technical output
with explicit shadow bindings; the permanent dialog implementation is unchanged.

`northstarSession.ts` is the only full-session request owner. It reads only
`/truth-spine/full-session`, omits credentials, rejects redirects, enforces a
four-second timeout and a 1 MiB streamed response limit, and schedules sequential
five-second reads. Unmount aborts the request and removes both timers. It calls
the complete session/factory validators, verifies canonical ASCII JSON factory
hashes, source-cycle age and time binding, and rejects session replacement,
regressing publication time or watermark. A rejected update never replaces the
last verified record. Retention is visibly STALE; the local display clock can
only degrade freshness, never grant authority or retimestamp evidence.

There is no fallback to the permanent compositor, fixtures, demonstration data,
legacy overview or a second polling owner. Static catalog names remain visible
when the projection is unavailable and are explicitly labeled configuration only,
not evidence or activity. Aggregates never create individual cases, dialogues,
agent invocations or movement. The architectural floor remains frozen because
the session metadata contract does not contain complete current case dossiers.
Characters are presentation only. The Case Library explains unavailable dossiers
and presents governed retained history instead of substituting the legacy 40-case
demonstration summary. Day Trading remains observation-only and fail-closed.

All 24 rooms, eight specialists, three governance entries, seven subsystems,
ten routing entries, L7/L8, Pattern Library, Jesse Judgment Bank, separate universe
captures, original clocks/classifications, limitations and incidents are reachable
through the existing destinations. Products and individual coverage inspection
use same-origin hash history while preserving the `fullSession=1` query. Missing
fields remain unavailable; routing credential presence is never probed.

### Isolated build and package

The dedicated build flag is `VITE_NORTHSTAR_FULL_SESSION=1`, with entry
`northstar-session.html`, base `/review/`, and no copied public fixture directory.
It is mutually exclusive with permanent/Expansion/engineering build gates.
The prospective route is:

`http://127.0.0.1:5291/review/northstar-session.html?fullSession=1`

That route is **not rendered-accepted or armed** until browser acceptance passes.
The uninstalled template selects this route. The engineering entry remains
available as a distinct build, never a silent fallback. Normal permanent outputs
must be compared independently; neither retained distribution is a build input.

`truth_spine_frontend_graph.py` validates the complete Northstar emitted graph.
Every asset must be inventory/hash-bound and reachable from the sole HTML entry.
Missing, extra, unbound, map, private-path and nonpackaged HTML references fail.
Unused moving portraits emitted by Vite despite tree shaking are pruned only in
this isolated mode; canonical source artwork is not changed. The full-day fixed
backend inventory includes the graph validator, and runtime package verification
still requires its independent source/runtime/provenance pins and owner modes.

The offline builder supports `--northstar`. Precommit development uses the
explicit `--source-review-only` mode, which byte-binds the uncommitted input tree
and emits `iios-source-review-build-NOT-INSTALLABLE`. Production verification
rejects that schema. This permits precommit testing without falsely labeling a
dirty tree clean. After authorized checkpoint, new clean builds and their new
commit-bound attestations remain mandatory; review attestations cannot be promoted.
No dependencies are installed or fetched. Build roots and retained outputs remain
owner-only; the original source and dependency trees are never build destinations.

### Acceptance and current blocker

The focused offline tests include an actual publisher-to-browser-validator
integration, graph tampering, one sequential polling owner, stale retention,
identity mismatch, bounded response, source-only provenance rejection, disabled
authority, fixed catalogs and independent permanent/engineering entrypoints.

`truth_spine_northstar_browser.py` is an explicit fixture-only acceptance utility,
not the full-session runner. It has no scheduler, operational state imports,
provider or credential boundary. Its seed is labeled `OFFLINE_FIXTURE_NON_LIVE`.
It proposes a temporary listener on 5291 and owned Safari WebDriver on 5292;
tests must record actual inner viewports, screenshots and navigation/focus results,
then close only their owned browser session and listener. It does not arm Friday.

Execution review rejected this fixture-browser command twice, treating port 5291
as prohibited by the source-only boundary despite the 3.6C fixture-acceptance
section. No fixture listener, Safari session or full-day runner was started.
Do not bypass that rejection by changing ports or using another launcher.
Browser measurements and visual acceptance are therefore pending clarification.
Source changes must remain unstaged/uncommitted until this mandatory gate and
all final noninterference gates pass. Permanent production remains YELLOW.
### Superbatch 3.6C.1 — Gallery required-text acceptance

The first Safari attempt's 17 scroll-size flags were preserved. A new fixture-only
diagnostic captured all 18 architectural buttons at an actual 1512×825 viewport:
each flagged button had complete required text inside its clipping ancestors;
oversized decorative portrait descendants caused its scroll-size overflow. The
unflagged External Intelligence station had no oversized portrait. Each button's
text ranges, clipping ancestors, decorative bounds, focus and screenshot are
retained in the isolated C.1 diagnosis evidence; none of the failed evidence was
modified. Architectural stations remain distinct from the 24 governed product rooms.

The isolated Gallery now includes the existing canonical 24-room panel, also used
by Expansion Wing. No room identity or projected value changes. The acceptance
detector measures text-node Range rectangles against actual clipping ancestors,
excludes only semantically hidden/decorative text, and detects text overlap. It no
longer equates decorative button scroll bounds with required-text clipping.
Browser regression probes must catch genuine clipping/overlap while accepting
wrapped long names, nested spans, aria-hidden decoration and collapsed disclosures.
Native WebDriver clicks, keyboard Escape/focus restoration, all coverage identities,
refresh restoration and observed polling intervals are required at every width.

This remains source-only plus fixture-only browser acceptance; no full-day session,
operational fixture substitution, credential access, permanent deployment or arming
is authorized. Checkpoint remains conditional on all validation and cleanup gates.
### Superbatch 3.6C.2 — owned history entry and layered Escape

The C1 failure was reproduced using its unchanged bundle after the complete
Gallery/Command selection path. Safari delivered trusted `Escape` keydown events
to the selected history disclosure; the React close handler ran exactly once.
Its first operation, `history.pushState`, threw `SecurityError: Attempt to use
history.pushState() more than 100 times per 10 seconds`. Because state clearing
followed that call, the exception left the panel and route unchanged. Both native
element key delivery and WebDriver keyboard Actions showed the same failure.
This was neither a wrong key nor a swallowed event or a route-reopen listener.

Each newly opened coverage panel now owns one marked selection history entry.
Closing traverses that owned entry with Back instead of creating another entry;
direct-hash entries use replace, never Back to an unrelated page. Panel state is
cleared idempotently before history effects. Browser rejection is reported without
granting authority or preventing closure. Opener identity survives rerenders;
post-render focus returns to the exact button (including a scoped fallback for
direct navigation). ARIA expanded/controls and the labelled region track visibility.

A single scoped React key handler processes only unmodified, non-repeated,
non-composing Escape/Esc keydown. An open disclosure containing focus closes first
and retains focus on its summary; the next Escape closes the panel. Closed-panel
Escape is harmless. No document-wide keyboard listener, fixture modification,
navigation throttling workaround or acceptance slowdown is introduced.

`northstarNavigation.ts` is the narrowly added presentation/navigation utility;
it carries no data, provider, credential or authority capability. Its focused tests
and native browser layer tests accompany the unchanged C1 text-clipping detector.
All prior failed evidence and C1 hash-bound evidence remain retained unchanged.
# Superbatch 3.6C.3 — scoped Gallery explanation flow

## C5 service-core and heading reconciliation

The retained architectural service-core box had absolute placement and z-index
15, covering the right-hand content after the C3 grid reflow. The isolated
Northstar export now wraps it in an aria-hidden, pointer-inert scene at local
z-index 0. Building isolation and floor contexts at z-index 1 prevent its
descendants from painting over station text, focus outlines or hit targets.
The permanent export is unchanged.

Desktop heading diagnostics showed three offscreen line boxes above their
factory, and two intersections with the preceding narrative label. The values
persisted at scrollY zero, but scrolling the same heading into view produced
correct in-factory bounds and a fully visible screenshot without data edits.
These were scroll-dependent legacy-layer geometry findings, not decorative or
focus-outline text. Medium/narrow stationary headings had no such flags.
Northstar's content-flow heading now removes the legacy positioned/parallax
layer. Clipping tolerances and text inclusion rules are unchanged; acceptance
must still reject any heading clipping or overlap after the repair.

The browser checks local stacking and pointer exclusion in addition to text
geometry. Negative probes retain rejection of foreground decoration and pointer
interception; harmless below-content decoration and long wrapped headings are
separately tested. No projection values, identities or authorities are changed.

The C2 medium-width failure was genuine: 16 architectural-station explanation
text ranges exceeded a 12.5px `max-height:2.5em; overflow:hidden` box. At narrow
widths a separate inherited rule hid the output block; zero clipping there was
not proof of complete visible information. The station floors and cards also
used absolute, fixed-height placement, so removing the text cap alone could
move text into neighboring content.

Only the isolated `.northstar-full-session` presentation now makes those floors,
room grids, cards and required output blocks content-driven. Grids reflow 3/2/1,
text wraps without a maximum height, explanatory text is 14px with 1.5 line
height, and card/grid padding reserves the focus outline. Required output and
legend text are not hidden on narrow screens. The existing 24 product-room
identities and descriptions, canonical artwork, C1 detector and C2 keyboard
repair are preserved. Permanent Museum CSS and data contracts are unchanged.

Fixture acceptance must compare text/ancestor bounds, neighboring cards and
focus at actual 1512/1020/386 widths. Build/test success alone does not approve
this presentation or authorize a full-day session.

### C6 — nested scroll and measurement settlement

C6 diagnosed the heading displacement as real internal scrolling, not a font
or screenshot-only false positive. After document scroll returned to zero,
the `overflow:hidden` factory retained scrollTop 96 at desktop. Its heading
was exactly factory top + 16px padding - 96px internal scroll. In-view heading
navigation reset that internal scroll to zero. Both states were stable across
animation frames with loaded fonts. Cropped screenshots and complete scroll
container evidence are retained outside source control.

The isolated factory uses `overflow:clip`: decoration remains clipped, but
focus/scrollIntoView cannot create an unintended inner scroll position. No
heading or fixture text is removed. Gallery checks all 18 station explanations
and 24 governed room mappings, then verifies zero internal factory scroll.

The fixture-only Safari harness waits for destination selection, rendered data,
font/image readiness and two consecutive equal frame pairs. Animation and
transition freezing is scoped to the acceptance page, not production source
styles. All viewport, document and nested scroll coordinates are recorded.
The bounded settlement timeout preserves samples and fails closed. Text and
ancestor rectangles carry a checked viewport-CSS-pixel coordinate contract.
Screenshots are bracketed by identical geometry snapshots; changes fail rather
than becoming an accepted capture. Hidden/inert destinations are excluded only
while inactive and checked after navigation. Existing real clipping, overlap,
decoration and focus checks remain mandatory.
### Superbatch 3.6C.7 — immutable fixture captures and evidence-spine underlay

The C6 fixture server reconstructed publication timestamps and the factory hash
per poll. An identical-looking generation could therefore change text geometry
during a screenshot. The fixture-only Safari runner now constructs one projection
before listening and binds its immutable bytes, source cycle, generation,
publication time and content hash into its startup receipt. Every data response
retains those bytes, including intentionally rejected HTTP responses.

The fixture browser uses a separately hashed, localhost-only clock bootstrap,
loaded before the unchanged compiled application. This is explicitly a fixture
HTML wrapper, not byte-identical packaged HTML: both HTML hashes and the bootstrap
hash are recorded separately. Native timers, polling cadence and performance
measurements remain real. The browser admission clock is fixed to the fixture
timestamp; advancing it 16 seconds tests the unchanged 15-second stale rule.
Production entrypoints, polling, authority, admission and freshness rules are not
modified. Native wall-clock screenshot times are recorded separately.

Each screenshot binds the visible identity fields and the read-only committed
React context that supplies them, before and after capture. Both content identity
and exact geometry must match. Rejected images remain incident evidence but never
enter accepted capture totals. Separate tests reject timestamp/hash/generation
changes, altered response bytes and genuine layout changes.

The evidence spine now shares the Northstar-only decorative underlay with the
service core. Its complete local stacking context stays below required floor
content, controls and focus outlines, with pointer events disabled throughout.
Permanent factory markup is unchanged. Rendered detection continues to reject
escaped spine layers, elevated decoration, pointer interception, text clipping
and genuine content overlap. Policy focus captures are required at all widths.

### Superbatch 3.6C.8 — complete decorative-layer census

The retained C7 bundle's route had a sibling stacking context at z-index 21,
above the content floors at 1. Same-frame Safari measurements show it crossing
Monitoring, Learning and Judgment text/control rectangles. At narrow width the
foundation's percentage height also crossed Expansion and the MAX labels. The
C8 diagnostic preserves all seven destinations at three actual viewport widths,
including generated pseudo-elements, containing blocks, stacking chains,
transforms, pointer settings, required-text/control/focus intersections and crops.

Northstar alone moves roof, route and foundation into the existing bounded,
aria-hidden scene at local layer 0, alongside the core and evidence spine.
Floors and walkway remain sibling content layers at 1. Internal room machinery
and floor/walkway rails are local underlays; labels retain their foreground
layers. Decorative descendants and generated ornament do not receive pointers.
No required station, room, label or control is removed. The default permanent
factory export and permanent stylesheet remain unchanged.

The census compares the first differing stacking contexts, not unrelated leaf
z-indices. A geometrically intersecting layer below content is recorded as a
harmless underlay, while paint above text, controls or focus fails. A control's
own background is distinguished from its separately measured text and outside
outline. Native hit testing records actual pointer interception independently
of enabled pointer settings. Pseudo-elements are measured from their computed
containing-block offsets when resolvable, otherwise conservatively bounded by
their host. Hidden/inert/collapsed content is excluded only while inactive.
Unknown same-context paint ordering is not silently accepted.

Offline stacking-order regressions and fixture-browser adversarial probes cover
visible obstruction, pointer interception, focus, pseudo-element paint, harmless
underlays and inactive-to-active destinations. Every accepted screenshot keeps
the census, geometry and immutable fixture identity binding. Monitoring, Learning
and Judgment receive native click, dialog, Escape and exact-focus-restoration
checks at all three widths. Fixture-only CSS probe nodes are removed in finally;
they do not mutate application data, source or production presentation.

### Superbatch 3.6C.9 — owned station dialogs

The C8 station census exposed inherited content-box dialog widths plus padding,
placing headings and close controls outside the visible viewport. The dedicated
Northstar graph does not import the permanent entrypoint's global sizing reset.
C9 uses a named Northstar dialog surface with explicit border-box sizing, a
bounded responsive width, viewport-contained safe-area margins and maximum
height. The heading and native close control occupy a non-scrolling header.
One min-height:0 body owns all long content scrolling; required content is not
shortened or hidden. Canonical portraits and quiet/evidence content are retained.

The additionally modified focus utility exports activateNorthstarDialog without
changing legacy activateDialog behavior. It owns a reference-counted document
scroll lock and topmost modal token, restores prior inline properties and their
priorities, inert/aria-hidden state and exact background scroll, and restores
the opener with preventScroll. Visible tab stops include disclosure summaries;
native focus can scroll the owned body to a previously offscreen target. Escape
is topmost-only and idempotent; cleanup removes the exact owned listeners.

All 18 dialogs are measured at top/bottom for each actual viewport before repair.
Acceptance measures surface/backdrop/header/body/close geometry, scroll metrics,
semantics, focus, text ranges and document styles. It expands disclosures through
native clicks, traverses the internal scroll region, proves required text
reachability, native close and Escape, reopen-at-zero and exact scroll/focus
restoration. Full raw text ranges are retained; paint overlap checks intersect
them with actual scrollports rather than treating intentionally scrolled-away
content as paint over the fixed header. Local hidden/clip violations still fail,
as do unreachable text, horizontal overflow and offscreen close controls.

The cumulative allowlist gains only dialogAccessibility.ts, a directly authorized
focus/scroll-lock utility. No backend truth, fixture data, station identities,
authority or permanent presentation behavior changes in C9.

### C10 — Station heading typography and visible keyboard focus

The retained C9 Radar body heading inherited Georgia 86px at .92 line-height:
79.12px line advance for 98px text ranges. Settled native Safari measurements
confirmed 19px overlapping line boxes, with static positioning, no transforms,
positive margins and no duplicated content. This is separate from the fixed
header title. Northstar-only dialog heading rules now use content-driven height,
natural wrapping and 1.4 line-height, retaining every original word and status.
No fixture, identity, classification, authority or global typography is changed.

Safari's owned Shift+Tab focus on summary did not match :focus-visible and had
outline-style none. Every focused Northstar station-dialog element now gets an
explicit gold 3px outline with 3px offset, including the initial heading and body
region. The modal owns the full logical Tab/Shift+Tab cycle independently of the
platform preference for tabbing buttons; native focus scrolls the body, with
scroll margins/padding retaining the ring. Background locking, topmost Escape
and exact opener restoration remain unchanged.

Acceptance records individual heading text-node ranges and grouped rendered
lines, computed typography and ancestors, neighboring rectangles, loaded fonts,
focus identity/name/role, outline bands, clipping ancestors, header and decoration
obstruction, conservative contrast against ancestor solid/gradient colors, and
generation-bound screenshots at each step. It traverses complete collapsed and
expanded Tab and reverse cycles for all 18 dialogs, opening disclosures through
keyboard Enter. Missing, clipped, covered or unproven-contrast focus fails closed;
activeElement alone never establishes visible focus. Existing required-text and
decoration detectors are not disabled or given wider tolerances.

C10 source scope is the Northstar stylesheet, owned dialog focus utility, focused
frontend tests, fixture Safari runner and this document. C1–C9 evidence is retained.
Source validation is not rendered approval: any mandatory Safari failure stops
the batch before staging or checkpoint, with verified owned-process cleanup.

### C11 — Native station traversal and explicit focus modality

The C10 Research result followed programmatic setup focus, not native traversal.
Fresh fixture-only Safari traces distinguish trusted Tab/Shift+Tab, element
send-keys, Option+Tab, programmatic focus, pointer activation, restoration,
fixture-poll rerender and destination navigation. On this Safari configuration,
plain Tab skipped implicit station buttons; a disposable explicit-tabindex
native button was reached. Option+Tab reached all 18, but is not plain-Tab proof.
No Safari/system preference was modified. C11's initial diagnostic artifact
inherited a success label despite being diagnostic-only; it is preserved, not
rewritten, and is not acceptance evidence. All diagnostic modes now explicitly
finish DIAGNOSTIC_ONLY and never authorize a checkpoint.

Northstar's isolated station renderer preserves native button semantics, full
catalog identity/content and Enter/Space activation while explicitly declaring
type=button and tabindex=0. Legacy Room rendering remains untouched. Real focus
scrolls the card into view without assigning focus or changing tab order; an
explicit restored-focus marker suppresses scroll during exact restoration.

The scoped keyboard/restoration indicator retains the gold 3px outline with an
opaque 8px dark backing. Opacity and grayscale no longer dim the focused card.
Unavailable status remains explicitly labeled; this is not activity styling.
Only restored interactive station openers receive a temporary indicator marker,
removed on blur or pointer-down with owned listener cleanup. Pointer-only focus
is not passed off as keyboard focus; no blanket focus rule is added.

The fixture runner requires trusted, unmodified Tab followed by the actual target
focus event. Programmatic setup, pointer, Option+Tab, prevented events and wrong
identities cannot satisfy that predicate. Both 18-station orders are tested with
real keys, and dialogs open via native Enter and Space. Exact visible restoration
is measured after close and Escape. Contrast may use an actual measured opaque,
zero-blur shadow only when its spread surrounds the complete outline and filter
and opacity do not alter it; otherwise the conservative ancestor-color bounds
remain. Clipping and obstruction gates remain active.

C11 changes only isolated station markup/CSS, the owned restoration helper,
fixture-browser modality logic, focused tests and this document. C1–C10 evidence
is preserved. Source/build success never substitutes for full rendered acceptance.

## Superbatch 3.6E — consolidated candidate (acceptance pending)

This section supersedes implementation-as-acceptance implications in C1–C11.
Their reports, diagnostic labels, screenshots and build identities remain intact;
none proves the complete current candidate. C11 did not pass compilation: an
accidental extra `RoomView` opening nested the real exports. E removes only that
opening, restores module boundaries, and adds a parser/export regression.

The isolated layout has content-driven room/station height and a three/two/one
grid at 1100/700px. The service core, roof, route, foundation and evidence spine
share a pointer-inert local underlay below content. MAX and canonical portraits
are retained. Station dialogs and Collector Plaque share a border-box surface,
persistent heading/close row and one scrolling body. Legacy Museum consumers,
artwork and permanent CSS are not changed. Motion freezing is a source-owned
deny-only presentation contract, not an acceptance-injected style.

Northstar modal close callbacks are stable across projection updates. The modal
owner restores exact scroll, inline property priorities and inert/ARIA values.
Only the topmost layer handles Escape; modified Tab is not intercepted. Native
Enter/Space remain native. Cases/history are inline regions, with opener lookup
by stable identity on every history restoration. Duplicate or unknown openers
are not guessed. History write refusal has a visible bounded failure and never
triggers retries or full-page navigation. The isolated scene control truthfully
states that motion is frozen; it cannot imply resumed activity.

Every browser screenshot request (including focus images and crops) passes one
admission boundary: fonts and geometry settlement, viewport CSS-pixel geometry,
source/build/provenance and immutable fixture bindings, active element, observed
input modality, pre/post frames, timestamps and PNG hash. Geometry or identity
changes reject the image; diagnostic images cannot become acceptance. Text range
intersection is labeled conservative, not asserted to be rasterized glyph proof.
Clipping and obstruction still fail closed. Mandatory catalog content is checked
separately from inactive/collapsed layout. Scroll reachability accumulates each
required line rather than requiring an entire long paragraph in one viewport.

Native semantics, actual Safari traversal and rendered focus are separate proof
dimensions. Plain Tab, Option+Tab and programmatic focus cannot substitute for
one another. Fixture instrumentation records programmatic focus calls without
changing their behavior. Alternative focus indicators require an unfocused
baseline, changed paint, adequate geometry/contrast and no clipping/obstruction.
No Safari or macOS preference is changed.

Full source-review provenance is checked before output creation or listeners:
schema, content hash, current source inventory, locked dependencies/toolchain,
build policy, observation and complete output graph. This does not make a dirty
source-review package installable. Cleanup steps and evidence writers execute
independently; one exception cannot skip later cleanup. Identity mismatch means
no signal to that process and a RED result, never a relaxed shutdown predicate.

Disposition: C1–C4 identity/text findings remain regression inputs; C5–C8 scenery,
scroll-coordinate and capture-race findings are consolidated; C9–C10 modal and
typography findings use the shared Northstar contract; C11 modality observations
remain diagnostic only. E must independently pass the full frozen source/build
and browser sequence. Until that succeeds: no checkpoint, full-day session,
installation, promotion or permanent-runtime change is authorized by acceptance.

## Superbatch 3.6E.1 — settlement diagnosis, acceptance incomplete

The retained E timeout had loaded fonts and zero geometry frames; it did not
identify the blocked stage. E.1 instruments the existing font/image/frame chain
with monotonic stage timestamps, sanitized image state, visibility/focus, timer
and microtask probes, frame request/callback counters, and persisted geometry
progress. A separate outer watchdog writes diagnostic evidence independently
of an unresponsive WebDriver command. Failure-only screenshots are explicitly
NOT ACCEPTED and cannot contribute to rendered acceptance totals.

Two bounded fixture diagnostics completed the Radar dialog, including
collapsed-tab-2: one used small synchronous progress probes and one retained
the original asynchronous-script delivery. Neither reproduced the stall, so
neither image waiting nor animation-frame/async delivery is a proven cause.
No cause-specific repair is accepted. These are diagnostic results, not a
substitute for the complete three-viewport frozen-candidate acceptance.

A third diagnostic, intended to include the original 36 native-Tab captures
before Radar, failed the pre-start socket bind with address-in-use. It created
no browser output root or listener. The loop did not report which of the two
ports failed; a later clear-listener check cannot establish that retrospectively.
No retry, reuse option, port change, permanent-process signal, or source UI
change was used. Owned diagnostic processes exited; protected inventories and
retained evidence compared unchanged. Checkpoint and full acceptance remain
blocked. The full adversarial matrix, regression/build rerun, and complete
Safari acceptance have not been claimed for E.1.

## Superbatch 3.6E.2 — temporary listener lifecycle

The historical failed probe did not record its port or kernel socket state.
The prior diagnostic's final observation was at 11:02:09 UTC; the next
preflight began at 11:02:29 UTC and its runner started at 11:02:30 UTC.
This is not an exact bind/shutdown interval. Prior runner/WebDriver exit and
listener absence were recorded, but TIME_WAIT, IPv6 ownership and any transient
owner at the failed bind cannot be reconstructed. No historical owner or
settlement cause is inferred from absence of a later listener.

The disposable plain-socket bind probes are removed. Read-only lsof/netstat
inventories cover both configured ports and IPv4/IPv6; three consecutive
identical observations establish stable listener absence. The fixture server
performs one actual bind to IPv4 loopback. Its explicit SO_REUSEADDR preserves
the standard HTTPServer retired-address semantics; SO_REUSEPORT is false.
TIME_WAIT is recorded separately, never treated as a live listener. Unknown
listeners fail closed. A racing competitor makes the actual bind fail and
produces a port-specific incident; no bind retry is attempted.

The fixture's listener PID and exact loopback address are verified, and a
byte-identical fixture HTTP response is required. WebDriver startup records
SPAWNED_NOT_READY, verifies owned loopback listener(s), status readiness and
unchanged process fingerprint before publishing READY. These are distinct
states; a startup attempt is not a successful ownership receipt.

Partial startup uses the same independent reverse cleanup: browser session,
fingerprint-verified WebDriver exit, fixture shutdown/socket/thread closure,
driver-log closure, and consecutive IPv4/IPv6 listener-absence observations.
The external runner must then exit and close its log before publishing the
sequential-cycle completion receipt. The next cycle checks that receipt and
every prior PID before startup. No unknown/mismatched process is signaled.
No permanent process, port, authority, fixture or frontend behavior is changed.

Three bounded diagnostic cycles and a separate complete frozen-candidate run
remain required. Passing diagnostics do not prove the old settlement timeout's
cause or substitute for all-viewport acceptance.

E.2 cycle 1 stopped before Safari session creation: the WebDriver launcher PID
was not the listener PID. Read-only ownership evidence identifies the listener
as Apple's `com.apple.WebDriver.HTTPService` XPC executable, parent PID 1,
with IPv4 and IPv6 loopback sockets on 5292. The launcher fingerprint remained
unchanged. The current strict same-PID predicate rejected this topology; it
must not be relaxed into accepting arbitrary listeners or parent-PID-1 services.
Only the verified launcher was signaled during cleanup; the XPC listener then
exited, and consecutive socket inventories confirmed both ports clear.
Cycles 2–3, new builds and complete rendered acceptance were not started.
The remaining source scope is explicit authentication of Safari's observed
launcher/XPC relationship, including launch causality, executable identity,
pre-existing-helper rejection and safe ownership-bounded shutdown. The old
address-in-use and layout-settlement causes remain historically unproven.

### Revised E.2 — one transactional acceptance session

The revised authorization replaces real-port sequential diagnostics with one
fixture bind, one Safari launch, one WebDriver session across all viewports and
scenarios, and one reverse-order shutdown. Lifecycle adversarial cases use
in-memory processes/socket inventories, not destructive tests on 5291/5292.
Transaction state advances only after its receipt is persisted; duplicate
startup/session transitions fail. Receipt-write failures cannot skip independent
cleanup and evidence writers. Every capture retains its stable geometry sample
hashes as well as source/build, fixture, destination and pre/post bindings.

Safari can delegate its loopback HTTP endpoint to Apple's HTTPService XPC
process. The transaction records absence of existing Safari automation before
launch, pins the root-owned non-writable system executables and hashes, obtains
executable identity through proc_pidpath (not argv), and requires a single new
same-user helper inside the bounded launcher start window. Only the fixed Apple
XPC executable with parent PID 1 qualifies; arbitrary helpers, prior helpers,
wrong users, stale starts, wildcard addresses and duplicate owners are rejected.
Both IPv4/IPv6 loopback listeners must bind to that one verified process and
WebDriver must be ready. The receipt distinguishes launcher from XPC listener
and describes its bounded launch-transaction association rather than claiming
a parent/child relationship or a cryptographic XPC attestation.

Cleanup signals only the unchanged launcher fingerprint, never an unidentified
listener or the XPC helper directly. It then verifies launcher/helper exit and
stable listener absence. The outer owning process verifies its own runner exit
and log closure. All real browser actions remain fixture-only; the original
zero-frame settlement stall is NON_REPRODUCED, not assigned an inferred cause.

Revised E.2 validation stopped before any browser listener: TypeScript passed,
but five existing C6 settlement tests failed (59/64 focused frontend tests
passed). Their isolated VM supplies the accepted geometry/font/frame contract,
not a browser `window`; E.1 diagnostic instrumentation introduced an unguarded
window reference before the scheduling chain. Three tests consequently also
reported asynchronous activity after completion. The 37 focused Python harness
and lifecycle tests passed but did not cover that VM compatibility contract.
No frontend test or production component was changed to suppress the failure.
The next narrow repair must separate browser diagnostics from the portable
settlement core while retaining real-browser instrumentation and its watchdog.
The complete suites, new builds, Safari run and checkpoint remain blocked.

### Superbatch 3.6E.3 — portable settlement separation, validation stopped

Settlement decisions now live in a portable plain-record core with injected
clock, scheduler, readiness and telemetry dependencies. The core contains no
browser globals. It retains two matching adjacent geometry pairs, deadline
enforcement and structured zero/one-frame, changing-geometry, prerequisite and
identity-change classifications. Existing geometry-VM callers retain their
adapter without adding a fake window; real acceptance explicitly selects the
capability-checked browser telemetry adapter. Safari telemetry and the outer
watchdog remain separate from policy. No frontend test/component/CSS changed.

The five formerly failing tests and all focused C6 tests passed unchanged.
Focused Python testing ran 52 cases: 51 passed, one failed. The new adversarial
`test_adapter_exception_is_structured` shows that a synchronous exception from
the first scheduler call inside the readiness promise's fulfilled callback
escapes the outer try/catch. A rejection handler supplied as the second argument
to then does not catch an exception thrown by its sibling fulfilled handler.
The next narrow correction must catch that callback exception and resolve the
same structured failure/cleanup path without exposing exception text. No test
was weakened or skipped. Broader validation, builds and Safari were not started;
no checkpoint is accepted. The original browser stall remains NON_REPRODUCED.

### Superbatch 3.6E.4 — scheduler completion guard, validation stopped

Every first/later frame and deadline scheduler invocation now crosses one
guarded boundary for synchronous exceptions and promise rejections. An explicit
RUNNING/COMPLETING/COMPLETE guard fixes the result once, records sanitized stage,
error type, monotonic elapsed time, frame count, last geometry and identity, and
cancels frame/timer handles independently. Late callbacks cannot mutate the
completed result; late acquired handles are cancelled without rescheduling.
No exception message or stack is copied into the structured failure.

The exact E.3 failing test passed. Ten new tests for scheduler/cleanup failure
and completion races passed. The complete focused Python file ran 72 tests:
71 passed, one failed. The existing injected-scheduler success test awaits only
one host microtask before directly calling its captured frame callback. With
the guarded promise assimilation path, the callback is still null at that
point, yielding `TypeError: callback is not a function` in the test. This is
not evidence of a Safari failure or permission to relax settlement thresholds.
The test and failure are retained unchanged. Remaining validation and browser
startup stopped at this gate; no checkpoint or rendered acceptance is claimed.

### Superbatch 3.6E.5 — explicit test-owned scheduler registration

The injected scheduler already exposes the required boundary by storing the
frame callback when invoked. Only the tests and this document change: the
runner, production scheduling, guarded exception path and geometry thresholds
remain byte-identical to E.4. Tests now await a local registration signal,
racing structured completion instead of assuming one or eight microtasks.
Test callbacks are invoked only after registration. Separate invocation and
cancellation signals cover rejected schedulers and late acquired handles.
Waiters are removed on completion, and an independent bounded test deadline
detects hangs without establishing readiness or adding production delays.

Explicit zero-, one- and multiple-microtask readiness inputs exercise the same
handshake. Missing registration is tested against the injected deadline and
must retain structured ZERO_FRAMES failure, serializable evidence and independent
cleanup. First/later throws, concurrent rejection, exactly-once completion,
late callbacks, cancellation and independent-run assertions remain enforced.
Rendered acceptance and checkpoint still require the complete frozen validation
and single-session Safari run; this synchronization repair is not browser proof.

### Superbatch 3.6F — bounded autonomous acceptance repair

Iteration 1: a diagnostic-only owned WebDriver run established that the configured
helper resolves under Cryptexes/OS while the kernel reports its exact counterpart
under Cryptexes/Incoming/OS. The executable bytes match, the helper is parented by
launchd, and its designated identity is com.apple.WebDriver.HTTPService with an
Apple anchor. The original path-equality gate rejected that unmodeled transition.
No browser session opened and cleanup/noninterference passed.

Ownership now requires exact configured role/loopback port, startup receipt,
PID/PPID/UID/start time, three stable observations, executable SHA-256, strict
executable signing against the exact Apple identifier, and an exact complete
root-owned non-writable helper bundle inventory. Only the corresponding
OS-to-Incoming/OS Cryptex path is modeled; arbitrary path or binary transitions
remain rejected. Apple's obsolete resource-envelope omit rules are not claimed
as validated: executable signing is checked separately and all four helper
bundle files are independently hash/mode/ownership bound to the configured pin.
Unknown or pre-existing automation blocks startup. Only the verified launcher
may be signaled; a helper is never directly signaled. Rejected kernel identities
are persisted before admission so a later failure remains diagnosable.

This source change does not authorize permanent services or full-day startup.
The append-only isolated repair ledger and complete frozen validation/browser
evidence determine acceptance, not source tests alone.

Iteration 2: live Safari ownership passed; Radar, Research and Policy dialogs
passed at desktop. Macro exposed required character names/roles below a zero-
height cinema. The new bounded body retained shrinkable inherited cinematic flex
rows, while each article's portrait aspect ratio constrained its caption box.
Northstar-only content-sized grid rows now reserve the multi-cast stage's full
height, keep original portrait geometry, and place captions and quiet evidence
in separate normal-flow rows. The permanent stylesheet and assets are unchanged.
The clipping detector still rejects the exact observed failure geometry. The
entire frozen validation and single-session browser run must repeat.

Iteration 3: the second run stopped on exact screenshot geometry inequality in
Research's expanded reverse-focus cycle. The outer dialog, active control and
viewport did not change; 554 descendant boxes changed as the content width
increased by exactly 17 CSS pixels during capture. The diagnostic image shows
the scrollbar absent, consistent with native automatic scrollbar gutter removal.
Northstar's owned scrollport now uses an explicitly dimensioned, visible styled
scrollbar and always reserves vertical scrolling. No scrollbar is hidden and no
geometry equality tolerance is added. The unaccepted screenshot and complete
before/after geometry remain preserved. All validation and rendering repeat.

Iteration 4: Research passed the prior screenshot mismatch. A later capture
after Policy close correctly failed because document.hasFocus() was false,
despite visible document and unchanged expected opener. The harness now records
and acquires the exact session-owned WebDriver window before starting settlement.
At most one explicit window selection is permitted, with bounded observed focus
readiness. URL, handle, fixture identity, active element and all owned scroll
positions must remain unchanged; any context change fails. This does not alter
document.hasFocus, relax settlement prerequisites, retry a rejected image or
turn a completed failure into success. The actual cause of OS foreground loss
was not retained and is not attributed to the user or an application.

Iteration 5: the owned WebDriver handle was insufficient to bring an occluded
native Safari window forward. At External's fifteenth disclosure the document
became hidden and unfocused; one WebDriver selection left both false throughout
the bounded observation. Cleanup and protected baselines passed. The fixture
runner now records a native window ID after matching exactly one current-tab URL
to its isolated page. Foreground acquisition requires that same ID and exact
current fixture URL, brings only that window forward, and then independently
requires actual document visibility/focus plus unchanged handle, fixture identity,
active element and scroll. It never selects an unrelated tab or changes focus
measurements. Missing, ambiguous or changed window bindings fail closed; native
automation errors are sanitized and bounded. No power setting is changed.
