# Batch 8G — Factory Intelligence UI

Batch 8G turns the Batch 8 intelligence stack into one governed operating surface.

## Release state

- Integrated IIOS version: `0.20.0`
- Integration commit: `c186468d3259680a8f081646fe473fc262cdb141`
- Factory UI contract: installed
- Full backend regression: passed during autonomous integration
- Frontend production build: passed during autonomous integration
- Live API smoke: passed during autonomous integration
- Live execution authority: `false`

## Purpose

The UI is a read-only view over actual IIOS state. It does not create research facts, resolve evidence gaps, qualify a trade, size capital, authorize an order, or execute a trade. Missing backend data is displayed as `UNKNOWN`, `PENDING`, `UNAVAILABLE`, or `OFFLINE`.

## Live contract

- `GET /experience/factory-intelligence/status`
- `GET /experience/factory-intelligence/overview`
- `GET /experience/factory-intelligence/case/{case_id}`

The overview consolidates:

- Batch 8D–8G release state
- Factory rooms and recent ledger movement
- Eight specialist desk roster and activity
- Governed cases and their current factory stage
- IIOS/OpenAI, Kimi, and Grok council views
- Model divergence and Skeptic escalation state
- Task-specific Batch 8F calibration
- Production universe, Fed feed, Kimi, and Grok gates
- Permanent paper-mode and live-capital locks

## Experience rooms

1. **Command** — operating picture, pipeline, council, gates, cases, calibration, and safety.
2. **Factory** — live rooms, desks, event rail, and the existing governed conveyor.
3. **Research** — model council, provider gates, opportunity discovery, and Jesse intelligence.
4. **Cases** — case queue, evidence-to-paper journey, model views, and underwriting controls.
5. **Capital** — paper capital control, risk authority, and execution locks.
6. **Judgment** — task calibration and the professional interview/Judgment Bank portal.

## Permanent authority boundary

The Factory Intelligence UI always reports:

- `read_only = true`
- `context_only = true`
- `qualification_evidence = false`
- `gap_resolution_eligible = false`
- `fact_resolution_authority = false`
- `committee_override = false`
- `risk_override = false`
- `capital_authority = false`
- `trade_signal = false`
- `auto_trade_authority = false`
- `paper_order_permission = false`
- `trade_execution_permission = false`
- `live_execution = false`

Committee and deterministic Risk remain authoritative.
