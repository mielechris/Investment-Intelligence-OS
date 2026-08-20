# Strategy Reverse Engineering Protocol

## Purpose

Study public trading behavior without pretending to know undisclosed logic exactly.

## Inputs

May include:

- public holdings;
- public trade disclosures;
- interviews;
- fund letters;
- academic descriptions;
- observable bot signals;
- public performance;
- public position timing.

## Required Unknowns

Document:

- hidden hedges;
- hidden derivatives;
- undisclosed exits;
- execution timing;
- capital constraints;
- tax considerations;
- leverage;
- discretionary overrides;
- reporting delay.

## Workflow

```text
Observed behavior
→ Candidate strategy family
→ Competing explanation
→ Formal hypothesis
→ Reconstructed rules
→ Historical test
→ Robustness test
→ Forward paper test
```

## Candidate Strategy Families

Examples:

- trend;
- mean reversion;
- event-driven;
- macro;
- sector rotation;
- volatility;
- carry;
- value;
- momentum;
- flow following;
- policy-event trading.

## Prohibition

Do not call a reconstruction “the bot’s algorithm” unless the exact rules are publicly disclosed and verifiable.
