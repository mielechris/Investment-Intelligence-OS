# Investment Intelligence OS
## Package 06 — Research — v0.1

**Destination:** `docs/06_research/`  
**Governing packages:** 01 Project Charter, 02 Architecture, 03 Specifications, 04 Data Catalog, 05 Agent Cards  
**Operating mode:** Research, backtesting, scenario analysis, and paper trading only

---

## Purpose

This package defines how IIOS tests whether an apparent market edge is real.

It governs:

- hypothesis formation;
- point-in-time datasets;
- event studies;
- baselines;
- backtesting;
- walk-forward testing;
- holdout discipline;
- regime analysis;
- execution costs;
- parameter sensitivity;
- reverse engineering of public strategies and bots;
- portfolio-level research;
- scenario testing;
- paper-validation gates;
- calibration;
- promotion, pause, revision, and retirement.

The goal is not to generate attractive backtests.

The goal is to **disprove weak ideas quickly and promote only durable evidence-backed edges**.

---

## Research Files

| File | Purpose |
|---|---|
| `01_RESEARCH_CONSTITUTION.md` | Non-negotiable research principles |
| `02_RESEARCH_LIFECYCLE.md` | Idea-to-retirement workflow |
| `03_HYPOTHESIS_DESIGN_STANDARD.md` | How hypotheses must be written |
| `04_DATASET_MANIFEST_STANDARD.md` | Point-in-time dataset requirements |
| `05_POINT_IN_TIME_AND_LEAKAGE_PROTOCOL.md` | Leakage prevention |
| `06_EVENT_STUDY_FRAMEWORK.md` | Event-driven market research |
| `07_BASELINE_AND_BENCHMARK_STANDARD.md` | Mandatory simple comparisons |
| `08_BACKTESTING_STANDARD.md` | Historical simulation requirements |
| `09_WALK_FORWARD_AND_HOLDOUT_STANDARD.md` | Out-of-sample discipline |
| `10_EXECUTION_COST_AND_CAPACITY_MODEL.md` | Fees, spread, slippage, capacity |
| `11_PARAMETER_SENSITIVITY_AND_ROBUSTNESS.md` | Fragility tests |
| `12_REGIME_RESEARCH_FRAMEWORK.md` | Performance by market regime |
| `13_STRATEGY_REVERSE_ENGINEERING_PROTOCOL.md` | Public strategy/bot analysis |
| `14_POLICY_SIGNAL_RESEARCH_PROGRAM.md` | Presidency, Congress, agencies, courts |
| `15_MACRO_AND_FED_RESEARCH_PROGRAM.md` | Rates, Fed, inflation, labor, liquidity |
| `16_GEOPOLITICAL_RESEARCH_PROGRAM.md` | War, sanctions, trade, diplomacy |
| `17_WEATHER_AGRICULTURE_COMMODITY_PROGRAM.md` | Weather, crops, livestock, commodities |
| `18_CORPORATE_AND_SUPPLY_CHAIN_PROGRAM.md` | Companies, capex, suppliers, sectors |
| `19_PUBLIC_FLOW_RESEARCH_PROGRAM.md` | Public holdings and positioning |
| `20_MARKET_STRUCTURE_RESEARCH_PROGRAM.md` | Trend, volatility, options, liquidity |
| `21_MULTI_SIGNAL_ENSEMBLE_RESEARCH.md` | Combining independent evidence |
| `22_SCENARIO_RESEARCH_LIBRARY.md` | Stress and branch testing |
| `23_PAPER_VALIDATION_PROTOCOL.md` | Forward validation |
| `24_PERFORMANCE_AND_RISK_METRICS.md` | Required reporting metrics |
| `25_CALIBRATION_AND_ATTRIBUTION.md` | Confidence and process attribution |
| `26_RESEARCH_PROMOTION_AND_RETIREMENT.md` | Governance for strategy status |
| `27_RESEARCH_EXPERIMENT_REGISTRY.md` | Experiment record standard |
| `28_RESEARCH_REPRODUCIBILITY_CHECKLIST.md` | Rebuild requirements |
| `29_RESEARCH_REVIEW_TEMPLATE.md` | Standard review template |
| `30_RESEARCH_ACCEPTANCE_CHECKLIST.md` | Package completion checklist |

---

## Promotion Ladder

```text
Idea
→ Registered Hypothesis
→ Exploratory Research
→ Controlled Historical Test
→ Validation
→ Holdout / Walk-Forward
→ Forward Paper Monitoring
→ Promoted Paper Strategy
→ Future Limited Live Review
```

No stage may be skipped merely because historical performance looks strong.

---

## Research Rule

Every research result MUST answer:

1. What was the hypothesis before the final test?
2. What information was actually available at decision time?
3. What simple baseline was beaten?
4. What happened after realistic costs?
5. What happens in bad regimes?
6. How sensitive is the result to parameters?
7. How large is the sample?
8. What contradicts the thesis?
9. What would cause the strategy to be retired?
10. Can another person reproduce the result?
