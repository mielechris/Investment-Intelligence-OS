# Batch 9E — High-Speed Market Radar

## Objective

Increase IIOS discovery throughput without lowering the governed case, Committee, Risk, Capital, sizing, authorization, or paper-execution gates.

Batch 9E is a research-discovery and case-throughput upgrade. It does not create trade authority.

## Current architecture

```text
Official S&P 500 + Nasdaq-100 governed universe
                 |
       Broad market radar sweep
    gainers / losers / most active
                 |
        strict-membership filter
                 |
        deterministic ranking
                 |
          +------+------+
          |             |
   Grok — The Wire   Gemini — The Books
   X + Web Search    Google Search grounding
   live narratives   URL Context
   crowding/chatter  structured evidence
          |             |
          +------+------+
                 |
        combined ranking only
                 |
       governed evidence check
      quote + current news only
                 |
        up to 5 case promotions
                 |
       up to 2 concurrent cases
          on 8-agent floor
                 |
            Committee
                 |
       existing 9B governed chain
 Risk -> Capital -> Sizing -> Paper Auth -> Paper
```

## Gemini model gears

### Rapid research — Gemini 3.7 Flash

Default endpoint: `gemini-3.7-flash`.

Used for the high-speed finalist lane with:

- Google Search grounding,
- URL Context,
- structured JSON output,
- medium thinking by default,
- parallel workers,
- source/query metadata captured for audit.

### Selective deep research — Gemini 3.1 Pro Preview

Default endpoint: `gemini-3.1-pro-preview`.

Only complex promoted finalists may be queued into the separate Gemini Pro worker. It uses:

- high thinking,
- Google Search grounding,
- URL Context,
- structured deep-research packets,
- primary-source and contradiction hunting,
- no decision or execution authority.

The deep worker is outside the radar critical path, so a difficult Pro investigation cannot stop the next market sweep.

## Grok role

Grok remains the real-time **Wire Room**:

- X Search,
- Web Search,
- breaking narrative,
- management comments,
- policy/regulatory developments,
- crowding/hype,
- contradictions and missing evidence.

Grok and Gemini launch concurrently after the deterministic radar sweep.

## Provider governance

Grok and Gemini can affect research priority/ranking only. Their output is explicitly marked:

- `context_only = true`,
- `qualification_evidence = false`,
- `fact_resolution_authority = false`,
- `capital_authority = false`,
- `trade_execution_permission = false`,
- `live_execution = false`.

A 9E opportunity can only be promoted after the existing deterministic opportunity gate receives real governed evidence from current market quotes/current news and clears duplicate-case controls.

## Continuous worker lanes

One 9E supervisor runs three independent lanes:

1. `RADAR` — broad discovery plus concurrent Grok/Gemini rapid research.
2. `CASE FLOOR` — up to two promoted cases through the eight governed IIOS desks + Committee.
3. `GEMINI PRO` — selective complex-finalist deep research outside the radar critical path.

## Default throughput bounds

- Broad production universe: verified official S&P 500 + Nasdaq-100 snapshot.
- Yahoo screener rows: up to 100 per radar category.
- Grok: 2 batches by default, 35 names each.
- Gemini Flash finalists: 8 by default.
- Gemini Flash workers: 4 by default.
- Promotion evidence finalists: 8 by default.
- Maximum case promotions per radar cycle: 5.
- Maximum concurrent cases on 8-agent floor: 2.
- Maximum Gemini Pro deep requests per radar cycle: 2.
- Radar cadence target: 5 minutes.
- Case-floor cadence: 30 seconds.
- Gemini Pro queue cadence: 60 seconds.

All limits are bounded and fail closed.

## Safety invariants

Batch 9E never grants:

- broker connectivity,
- live capital authority,
- Committee override,
- Risk override,
- Capital override,
- automatic live-trade authority,
- direct paper-order permission,
- live execution.

Batch 9B remains authoritative for any eventual governed mock paper position.

## Raw radar acceptance — 2026-08-26 PT

The first isolated acceptance ran `--once --dry-run --no-models` against a SQLite backup of the live ledger.

- Acceptance-only non-production universe: 282 symbols.
- Raw radar hits: 282.
- Model candidates: 0 by design.
- Promoted cases: 0 by design.
- Total radar cycle time: **16.745 seconds**.
- Live branch unchanged: true.
- Live tracked status unchanged: true.
- Runner exit code: 0.
- Result: **PASS**.

The 282 hits are raw screener candidates, not actionable investment cases. The temporary acceptance universe was explicitly non-production because the official index source encountered a local CA verification error.

## Provider migration note

The initial 9E prototype used Kimi as the second external research provider. Grok successfully passed live X/Web acceptance, while the Kimi Open Platform key was valid but provider execution was blocked by an insufficient-balance billing suspension. Kimi remains in the repository as an optional future adapter, but it is no longer on the active 9E critical path.

The active second-provider architecture is now **Gemini 3.7 Flash + selective Gemini 3.1 Pro**, chosen for Google Search grounding, URL Context, structured outputs, large-context research, and cleaner high-throughput integration.

## Model acceptance

`run_batch9e_model_acceptance.py` clones the successful raw-acceptance ledger into a second `/tmp` SQLite database and runs a fresh Grok + Gemini cycle with promotions disabled.

Acceptance breadth is bounded:

- Grok: one batch of up to 20 names with X Search + Web Search.
- Gemini Flash: up to 4 finalists with Google Search + URL Context, 2 parallel workers.
- Fresh model execution is required for PASS.
- No case promotions.
- No eight-agent case-floor work.
- No paper-order or live authority.

Only after this acceptance passes should continuous Grok + Gemini 9E be allowed to write research/case records to the shared governed ledger.
