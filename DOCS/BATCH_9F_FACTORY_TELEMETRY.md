# Batch 9F — Factory Telemetry + Continuous Opportunity Watch

## Objective

Close the observability gap between the local IIOS market test and remote
notifications without adding any new trading authority.

The source of truth remains the local `iios_ledger.db`. Batch 9F reads that
ledger in SQLite `mode=ro`, builds a sanitized state snapshot, and can publish
the snapshot outbound to a **private** GitHub issue. The Mac is never exposed
as an inbound public service.

## Factory flow

`9E radar -> Grok/Gemini -> promotion -> 8 agents -> Committee -> Risk -> 9B paper fund -> ledger -> 9F telemetry`

9F reports what the factory did. It does not make or change decisions.

## Snapshot contract

The snapshot includes only:

- 9E radar cadence, universe/hit counts, model candidate counts and promotions
- provider health/errors at a high level
- recent promoted cases and 8-agent completion count
- latest Committee, qualification and Risk state
- recent governed paper orders
- paper NAV, P&L, exposure and drawdown
- 9A/9B cadence health
- whitelisted meaningful audit events
- explicit paper-only safety invariants

It excludes raw prompts, raw evidence, API credentials, environment variables,
authorization tokens and any broker/live-capital capability.

## Remote transport

Preferred transport is an outbound update to one issue in a dedicated private
GitHub repository. The exporter refuses to publish when the target repository
is not private and only updates when the meaningful-state fingerprint changes.

Required local environment:

```text
IIOS_TELEMETRY_GITHUB_REPO=owner/private-telemetry-repo
IIOS_TELEMETRY_GITHUB_ISSUE=1
```

The local machine must have GitHub CLI (`gh`) authenticated for that private
repository.

Example continuous exporter:

```bash
python scripts/iios_factory_telemetry_exporter.py \
  --interval-seconds 60 \
  --output runtime/factory_telemetry.json
```

The remote alerting layer should treat this private issue as the source of
truth for claims labeled `FACTORY DETECTED`. Public-news research may still be
used as a comparison layer, but it must be labeled `EXTERNAL CATALYST` unless
the telemetry snapshot proves that IIOS detected and processed it.

## Success metrics

1. Opportunity detection latency
2. Promotion rate
3. Opportunity miss rate versus the day's meaningful market dislocations
4. Time from promotion to eight-agent/Committee completion
5. Committee/Risk decision-change rate
6. Paper order/fill count
7. NAV/P&L/drawdown
8. Radar, observation and paper-trading cadence reliability
9. Provider/data failure rate
