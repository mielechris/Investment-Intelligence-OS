# Decision Record Standard

## 1. When an ADR Is Required

Create a decision record when a change affects:

- system architecture;
- source of truth;
- data model;
- model authority;
- risk authority;
- live/paper boundary;
- source rights;
- security boundary;
- major dependency;
- provider lock-in;
- deployment topology;
- schema compatibility;
- research integrity;
- institutional scalability;
- operational recovery.

## 2. When an ADR Is Not Required

Routine implementation detail generally does not require an ADR when it does not alter a governed contract.

Examples:

- renaming a local variable;
- refactoring internal code without behavior change;
- fixing a typo;
- adding a test;
- changing non-material UI spacing.

## 3. Required Sections

Every ADR MUST contain:

- context;
- decision drivers;
- options considered;
- decision;
- rationale;
- positive consequences;
- negative consequences;
- risks and controls;
- implementation impact;
- validation;
- rollback/reversal;
- review trigger;
- final status.

## 4. Immutability

Accepted ADRs are not rewritten to erase old reasoning.

Corrections MAY be appended.

Material change creates a superseding ADR.

## 5. Linking

Every material implementation ticket SHOULD link to relevant ADR IDs.

## 6. Review

An ADR review asks:

- Are the original assumptions still true?
- Did costs or risks change?
- Did scale change?
- Did provider capabilities change?
- Did compliance needs change?
- Is the decision still the simplest sound choice?
