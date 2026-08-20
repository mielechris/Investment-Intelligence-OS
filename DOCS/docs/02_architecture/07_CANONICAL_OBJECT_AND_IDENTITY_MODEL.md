# Investment Intelligence OS
## Canonical Object and Identity Model — v0.1

---

## 1. Purpose

IIOS requires stable, vendor-neutral objects so that sources, models, brokers, and research tools can change without rewriting the domain.

Detailed fields belong in Package 04 — Data Catalog. This document defines the architectural object families and identity rules.

---

## 2. Identifier Rules

Every durable canonical object receives an opaque globally unique ID.

Rules:

- never use a ticker, URL, filing number, or provider ID as the sole primary key;
- preserve all external identifiers in mapping tables;
- IDs are immutable;
- merges and splits are audited;
- references use IDs, not display names;
- human-readable slugs may exist but are not authoritative.

Recommended implementation:

- UUID primary identifiers;
- UTC timestamps for ordering;
- unique constraints on source-specific natural keys;
- content hashes for immutable payload identity.

---

## 3. Core Object Families

### Source Objects

- `Source`
- `SourceEndpoint`
- `SourceCredentialReference`
- `SourceRightsPolicy`
- `ConnectorDefinition`
- `ConnectorCheckpoint`
- `SourceHealthAssessment`

### Ingestion Objects

- `RetrievalAttempt`
- `RawRecord`
- `RawArtifact`
- `ParseResult`
- `NormalizationResult`
- `RevisionLink`
- `QuarantineCase`

### Canonical Knowledge Objects

- `CanonicalEvent`
- `Entity`
- `EntityAlias`
- `EntityIdentifier`
- `EntityRelationship`
- `WorldStateSnapshot`
- `RegimeAssessment`
- `PolicyState`
- `MarketCalendar`

### Market Objects

- `Instrument`
- `InstrumentIdentifier`
- `Venue`
- `MarketDataPoint`
- `Bar`
- `Quote`
- `YieldCurvePoint`
- `VolatilityObservation`
- `CorporateAction`
- `FuturesContract`
- `OptionContract`
- `CryptoAsset`
- `CommodityDefinition`

### Evidence and Reasoning Objects

- `Evidence`
- `EvidenceLink`
- `Claim`
- `ClaimEvidence`
- `CausalChain`
- `CausalStep`
- `CounterChain`
- `Assumption`
- `Falsifier`
- `HistoricalAnalog`
- `MissingInformationRequest`
- `Hypothesis`
- `InvestmentThesis`
- `ExplainabilityPacket`

### Agent and Decision Objects

- `AgentDefinition`
- `AgentRun`
- `AgentOutput`
- `DebateRound`
- `CommitteeSession`
- `CommitteeDecision`
- `DissentRecord`
- `ModelDefinition`
- `PromptDefinition`

### Portfolio and Execution Objects

- `Portfolio`
- `PaperAccount`
- `CashBalance`
- `Position`
- `PositionLot`
- `ExposureSnapshot`
- `RiskPolicy`
- `RiskAssessment`
- `RiskDecision`
- `OrderIntent`
- `PaperOrder`
- `PaperFill`
- `ExecutionCost`
- `PortfolioSnapshot`

### Research and Learning Objects

- `StrategyDefinition`
- `DatasetManifest`
- `FeatureDefinition`
- `ResearchRun`
- `EventStudyRun`
- `BacktestRun`
- `WalkForwardRun`
- `ScenarioRun`
- `BenchmarkRun`
- `ResearchResult`
- `Postmortem`
- `OutcomeAttribution`
- `CalibrationRecord`
- `BeliefUpdate`

### Platform Objects

- `JobDefinition`
- `JobRun`
- `OutboxEvent`
- `InboxReceipt`
- `AuditEvent`
- `ConfigurationVersion`
- `ReleaseVersion`
- `Incident`

---

## 4. Entity Types

Initial entity types include:

- person;
- company;
- subsidiary;
- fund;
- government;
- government agency;
- central bank;
- legislature;
- court;
- country;
- region;
- port;
- sector;
- industry;
- technology;
- facility;
- commodity;
- crop;
- livestock species;
- disease;
- weather system;
- currency;
- index;
- instrument;
- economic indicator;
- law;
- regulation;
- executive action;
- contract;
- supply-chain node.

Entity type is versioned and extensible.

---

## 5. Entity Resolution

Resolution sequence:

1. exact external identifier;
2. authoritative alias;
3. normalized name plus type and geography;
4. relationship context;
5. probabilistic candidate generation;
6. confidence threshold;
7. human review for ambiguous high-impact matches.

A model may suggest a match.

Only deterministic rules or approved review may finalize a high-impact merge.

---

## 6. Merge and Split Rules

Entity merge:

- preserves both original IDs in history;
- selects a surviving canonical ID;
- redirects references through an audited mapping;
- records evidence and actor;
- supports reversal.

Entity split:

- creates new entities;
- reassigns relationships by explicit rule;
- preserves prior state and decision context;
- triggers affected-thesis review when material.

---

## 7. Time Model

IIOS uses both event time and system time.

### Event-Time Fields

- published;
- effective;
- market available;
- valid from;
- valid to;
- transaction or occurrence time.

### System-Time Fields

- created;
- observed;
- processed;
- superseded;
- deleted by policy.

This enables “what was true” and “what IIOS knew” queries.

---

## 8. Versioning Model

Objects with changing interpretation or state use explicit versions.

Examples:

- canonical event revision;
- entity relationship version;
- world-state snapshot;
- claim version;
- thesis version;
- risk-policy version;
- strategy version;
- prompt version.

Past decisions continue to point to the versions used at the time.

---

## 9. Classification Versus Identity

A classification may change without changing the object’s identity.

Examples:

- one event may be reclassified from “remark” to “announced intent”;
- one company may move sectors;
- one regime probability may change;
- one claim may become contested.

The original object remains identifiable.

---

## 10. Instrument Identity

An instrument identity must separate:

- issuer or underlying entity;
- instrument type;
- venue;
- currency;
- contract terms;
- expiry;
- strike;
- option type;
- multiplier;
- settlement;
- provider symbols;
- corporate-action lineage.

Tickers are aliases, not permanent identity.

---

## 11. Theme and Causal Cluster Identity

Portfolio concentration requires identity beyond sectors.

IIOS represents:

- policy theme;
- macro factor;
- commodity dependency;
- supply-chain dependency;
- geopolitical exposure;
- weather exposure;
- AI or data-center theme;
- interest-rate sensitivity;
- dollar sensitivity;
- shared causal event.

A position may belong to multiple clusters with weights and confidence.

---

## 12. Identity Acceptance Tests

- two provider symbols map to one canonical instrument;
- reused ticker does not overwrite an old instrument;
- ambiguous company names remain unresolved rather than silently merged;
- entity merge preserves old decision lineage;
- revised event does not erase original source interpretation;
- historical query returns the entity relationship known at that time;
- option and futures contracts remain distinct from underlyings;
- causal-cluster exposure survives symbol changes.
