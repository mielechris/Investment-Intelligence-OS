# Batch 9S — Agent Performance League

## Purpose

9S measures the eight specialist desks and model roles using persisted IIOS evidence. It is a scoreboard and diagnostic layer, not an authority layer.

## Persisted measurements available now

- 9J observations, decisive outcomes, aligned outcomes and alignment rate by agent.
- Average persisted agent confidence.
- 9G recent governed-case participation.
- Exact-lineage aligned downside-avoidance and adverse-call attribution when the agent actually received the case.

## Measurement gaps

9S does not fabricate metrics that are not persisted. The following remain unranked until instrumentation exists:

- per-agent research latency;
- per-agent evidence quality;
- Committee marginal influence/counterfactual contribution;
- cost per useful agent result;
- task-specific and market-regime-specific performance;
- Grok/Gemini/OpenAI/Kimi task accuracy, latency and cost under one common rubric.

## Miss attribution rule

A factory miss that never became a governed case and has no agent lineage is `UNATTRIBUTED_TO_AGENTS`. It cannot reduce any specialist score.

## Ranking maturity

- `WARM_UP`: no decisive persisted outcomes.
- `PROVISIONAL`: at least one decisive outcome, but fewer than 20.
- `OFFICIAL`: at least 20 decisive outcomes with a persisted alignment rate.

The displayed league score is the persisted 9J alignment rate. No weight change follows from rank.

## Model league

Grok, Gemini, OpenAI and Kimi appear in the browser but remain `UNRANKED_MEASUREMENT_GAP` until the internal model task/cost/latency telemetry proposed by 9R exists.

## Safety

9S has no authority to:

- change agent weights;
- change model routing;
- change Committee or Risk rules;
- alter capital authority;
- create trades or enable live execution.

Any future reweighting or routing proposal must flow through 9P analysis, 9Q shadow experiment, and explicit human approval.
