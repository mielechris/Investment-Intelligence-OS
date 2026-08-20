# Agent Evaluation Matrix

Every agent is evaluated before promotion and continuously during paper operation.

| Dimension | Description |
|---|---|
| Evidence precision | Claims cite the correct evidence |
| Evidence recall | Important available evidence is not missed |
| Unsupported-claim rate | Fraction of claims without support |
| Contradiction handling | Material contrary evidence is surfaced |
| Point-in-time integrity | No future information leaks backward |
| Abstention quality | Agent abstains when it should |
| Overconfidence | Confidence exceeds demonstrated calibration |
| Calibration | Confidence matches observed reliability |
| Prompt-injection resistance | Source text cannot change authority |
| Tool discipline | Only permitted tools are used |
| Mandate discipline | Agent remains in its domain |
| Counter-case quality | Strong alternatives are considered |
| Latency | Execution time |
| Cost | Model/tool cost |
| Stability | Regression consistency |
| Incremental value | Adds value over simpler baseline |

## Promotion Status

```text
DRAFT
EVALUATING
APPROVED_FOR_TEST
APPROVED_FOR_PAPER
PAUSED
RETIRED
```

## Minimum Promotion Evidence

An agent cannot enter paper workflows until:

- schema compliance passes;
- evidence citation tests pass;
- prompt-injection tests pass;
- abstention tests pass;
- tool-permission tests pass;
- regression suite passes;
- cost and latency are within policy;
- owner approves promotion.

## Calibration

Where outputs contain confidence, evaluate by confidence bucket.

High confidence with poor realized accuracy MUST reduce trust.
