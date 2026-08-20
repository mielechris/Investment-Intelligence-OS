# Initial Agents Implementation

Implement these three first.

## Policy Analyst

Input:

- policy event;
- policy state;
- evidence;
- world state.

Output must include:

- policy stage;
- implementation probability;
- beneficiaries/harmed parties;
- constraints;
- expected lag;
- counter-case;
- evidence citations.

Critical test:

```text
CEO meeting at White House != contract award
```

## Macro and Rates Analyst

Input:

- macro release;
- Fed event;
- yield curve;
- regime;
- market context.

Output:

- macro state;
- surprise;
- rate/liquidity mechanism;
- affected assets;
- contradictions;
- lag.

Critical test:

```text
historical replay uses original macro vintage
```

## Skeptic / Red Team

Input:

- thesis packet;
- specialist views;
- market context;
- research.

Output:

- strongest objection;
- alternative explanation;
- priced-in risk;
- leakage/overfit concern;
- crowding;
- risk-critical dissent.

Critical test:

```text
profitable recent story with weak causality must be challenged
```

## Promotion

Do not add more agents until these three pass:

- evidence tests;
- injection tests;
- abstention tests;
- structured output;
- latency/cost measurement.
