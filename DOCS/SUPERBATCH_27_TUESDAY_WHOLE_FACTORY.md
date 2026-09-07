# Superbatch 27 — Tuesday whole-factory commissioning

Status: `FIXTURE / NON-LIVE / NOT ACTIVATED`. This source batch does not migrate
the installed controller, release credits, read a credential, contact a provider,
create a candidate, or create a synthetic or operational position.

## Product plan

The Tuesday matrix covers all 24 registered product rooms. Ten fixed listed
instruments are future live-evidence pilots: MU, SPY, XLK, VNQ, TLT, GLD, UUP,
IBIT, PFF and BIL. Listed proxies remain explicitly proxies and never establish
direct bond, commodity, currency or crypto exposure.

Four rooms remain `LIVE_EVIDENCE_PENDING_IDENTITY`: U.S. mid-cap, U.S. small-cap,
developed-market and emerging-market equities. No ticker has been selected merely
to fill these slots. Provider support, exchange, security type, domicile, currency,
and exact identity require future owner review.

The remaining ten rooms are `STRUCTURAL_FAIL_CLOSED`: Treasury bills; Treasury
notes/bonds; investment-grade credit; high-yield credit; municipal credit; listed
equity/ETF options; index options; commodity futures; FX spot; and crypto spot.
Their registration, schema and failure behavior may be tested, but their source,
research, synthetic-observation and operational eligibility remain false.

Each of the 24 independent synthetic comparison accounts begins at a hypothetical
$10,000 basis. They are not pooled or deployable and are separate from the single
operational $10,000 paper fund. Missing performance remains null.

## Staged credit governor

The future daily hard ceiling is 200 credits, with zero currently released:

- Stage A — Core Release: at most 100, separately owner-authorized.
- Stage B — Evidence Expansion: at most 50 after Stage A review and a new approval.
- Stage C — Owner Reserve: at most 50 with reason, instruments, endpoints, calls,
  expected cost and expiry.

No stage auto-releases. Auto-reload, retries and browser invocation are prohibited.
Unknown endpoint cost fails closed; ambiguous outcomes are charged conservatively;
cache hits cost zero; request identities are immutable and deduplicated. Unused
budget never rolls forward automatically.

The v1 30-credit disabled state is not changed by this batch. The pure migration
contract accepts only an unambiguous, authority-locked, disabled state; preserves
request identities and accounting; increments sequence monotonically; changes the
schema explicitly; and leaves every v2 stage at zero release. Operational migration
requires separate authorization.

The deterministic Stage A draft contains 50 one-credit request identities: five
per pilot for an opening snapshot, point-in-time OHLCV, current fundamentals,
one intraday mark and one closing mark. Costs are fixture assumptions until the
Tuesday entitlement/cost preflight verifies every endpoint. Any unknown or higher
cost blocks compilation rather than spending the reserve.

## Scanner and candidate governance

The existing scanner and publisher remain the sole owners. Browser polling cannot
scan, publish or promote. Aggregate opportunity counts cannot create identities.
The required path is authenticated identity → immutable discovery time → evidence
lineage → governed case → human decision → Committee → Skeptic → Risk → separate
owner authorization. Professional observations require independent corroboration.

Human dispositions are `APPROVE_FOR_COMMITTEE_REVIEW`,
`DEFER_FOR_MORE_EVIDENCE`, `REJECT`, `SOURCE_NOT_ELIGIBLE`, and
`IDENTITY_NOT_AUTHENTICATED`. Even human committee approval cannot automatically
create a synthetic observation.

## Methods and reporting

All 16 methods are crossed with all 24 products for 384 explicit contracts.
Eligibility, provenance, adjustment basis, minimum sample, liquidity, costs,
benchmark, holding period, invalidation, risk and out-of-sample requirements are
recorded. Historical methods fail closed while adjustment treatment is unspecified.
One Tuesday session cannot establish method success, and all missing results remain
null.

The post-close schema is null-safe and separates scan counts, lineage, human and
Committee/Skeptic/Risk decisions, stage/request accounting, cache and ambiguous
reservations, synthetic observations, structural results, corporate actions,
operational paper activity, errors and next evidence needs. It cannot claim method
success, profitability, execution quality without bid/ask, adjusted historical
returns without an adjustment basis, or direct exposure from a proxy.

## Remaining gates

1. Human review of this source and isolated presentation.
2. Exact source checkpoint.
3. Separately authorized operational controller migration.
4. Authentic Monday September 7 `CLOSED_HOLIDAY` rehearsal.
5. Separate Tuesday Stage A owner authorization with a reviewed request plan.

No provider, Keychain, broker, ledger, order, execution, service-control or browser
mutation authority is introduced here.
