# Batch 9E — High-Speed Market Radar

## Objective

Increase IIOS discovery throughput without lowering the governed case, Committee, Risk, Capital, sizing, authorization, or paper-execution gates.

Batch 9E is a research-discovery and case-throughput upgrade. It does not create trade authority.

## Architecture

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
   Grok Wire Room    Kimi K3 Crew
   X + Web Search    Formula Web Search
   batch narrative   high-reasoning research
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

## Speed design

### 1. Broad radar instead of ticker-by-ticker news

The initial sweep uses a small number of broad Yahoo screener calls for:

- day gainers,
- day losers,
- most active.

Results are intersected with the existing verified official S&P 500 + Nasdaq-100 universe. This avoids hundreds of serial GDELT/news calls.

### 2. Grok and Kimi run concurrently

Grok and Kimi launch in parallel after the deterministic sweep.

Grok is used as the real-time **Wire Room**:

- X Search,
- Web Search,
- breaking narrative,
- management comments,
- policy/regulatory developments,
- crowding/hype,
- contradictions and missing evidence.

Kimi K3 is used as the rapid **Research Crew**:

- Formula Web Search,
- high reasoning,
- catalyst verification,
- primary/credible-source discovery,
- counterevidence,
- structural-vs-temporary assessment,
- unresolved research questions.

Neither model output is qualification evidence or fact-resolution authority.

### 3. Deep-context reuse

The top radar state is fingerprinted. If the important candidate set and move buckets have not materially changed, Grok/Kimi context can be reused for a bounded period rather than rerunning expensive research every radar cycle.

Default deep refresh window: 15 minutes.

### 4. Separate case-floor lane

Promoted 9E cases enter a separate queue. Up to two cases may run concurrently through the governed eight-agent orchestrator.

The radar does not wait for those cases to finish before beginning another sweep.

### 5. Selective Kimi native swarm

The native Kimi swarm is deliberately off the radar critical path. When configured, only sufficiently complex promoted finalists are queued for deep swarm research.

The swarm:

- may use subagents,
- uses high thinking,
- is context-only,
- has no IIOS repository write access,
- cannot qualify a case,
- cannot authorize capital,
- cannot create a paper or live order.

## Default throughput bounds

- Broad governed universe: official S&P 500 + Nasdaq-100 membership snapshot.
- Yahoo screener rows: up to 100 per radar category.
- Grok batches: 2 by default, 35 names each.
- Kimi rapid finalists: 12 configured in core; operator launch may start with 8 for latency testing.
- Kimi rapid workers: 4 by default.
- Promotion evidence finalists: 8 by default.
- Maximum case promotions per radar cycle: 5.
- Maximum concurrent cases on 8-agent floor: 2.
- Radar cadence target: 5 minutes.
- Case-floor queue cadence: 30 seconds.
- Kimi Swarm queue cadence: 60 seconds.

All limits are bounded and fail closed.

## Promotion authority

Grok and Kimi can affect research ranking only.

A 9E opportunity can be promoted only after the existing deterministic opportunity gate receives real governed evidence:

- current market quote,
- current news coverage,
- existing `score_candidate` promotion checks,
- no recent duplicate governed case for the ticker.

External-model context is stored separately and marked:

- `context_only = true`,
- `qualification_evidence = false`,
- `fact_resolution_authority = false`.

## Continuous worker lanes

One 9E supervisor process runs three independent threads:

1. `RADAR` — high-speed discovery and Grok/Kimi ranking.
2. `CASE FLOOR` — up to two promoted cases through the eight desks + Committee.
3. `KIMI SWARM` — selective complex-finalist deep research.

A slow swarm request therefore cannot block the radar or case floor.

## Safety invariants

Batch 9E never grants:

- broker connectivity,
- live capital authority,
- Committee override,
- Risk override,
- Capital override,
- automatic live-trade authority,
- paper-order permission outside the existing governed downstream system,
- live execution.

The existing Batch 9B chain remains authoritative for any eventual mock paper position.

## First acceptance

The first acceptance intentionally runs:

```text
--once --dry-run --no-models
```

It also uses a SQLite backup of the live ledger. Therefore:

- live Batch8 working tree is unchanged,
- live governed ledger is unchanged,
- Grok/Kimi are not called,
- no cases are promoted,
- no eight-agent case-floor work is started,
- no broker or execution authority exists.

### Raw radar acceptance result — 2026-08-26 PT

- Acceptance-only non-production universe: 282 symbols.
- Radar hits: 282 raw screener candidates.
- Grok candidates: 0 by design.
- Kimi candidates: 0 by design.
- Promoted cases: 0 by design.
- Total radar cycle time: **16.745 seconds**.
- Live branch unchanged: true.
- Live tracked status unchanged: true.
- Runner exit code: 0.
- Result: **PASS**.

The 282 hits are the raw acceptance candidate pool because the temporary fallback universe itself was built from the broad screeners; they are not 282 actionable cases. The result validates throughput of the new broad radar path.

The fresh official S&P/Nasdaq capture in this acceptance bootstrap encountered a local CA-certificate verification error. The fallback universe was explicitly marked non-production and was never allowed to promote cases or create any trading authority.

## Second acceptance

`run_batch9e_model_acceptance.py` uses the successful raw-acceptance ledger as its source, clones it to a second `/tmp` SQLite database, and then runs a model-enabled 9E dry run with promotions disabled.

Acceptance breadth is deliberately bounded while preserving full useful provider capability:

- Grok: one batch of up to 20 names, X Search + Web Search.
- Kimi: up to 4 finalists, provider model resolution, Formula Web Search, high reasoning, 2 parallel workers.
- Grok and Kimi run concurrently.
- No case promotions.
- No eight-agent case-floor run.
- No paper or live authority.

The launcher also resolves the certifi CA bundle from the IIOS virtual environment and exports it for provider HTTPS calls.

Measure:

- Grok availability and candidate coverage,
- Kimi availability and candidate coverage,
- deep-research latency,
- total cycle latency,
- provider degradation behavior,
- live checkout invariants.

Only after both acceptances should continuous 9E be allowed to write research/case records to the shared governed ledger.
