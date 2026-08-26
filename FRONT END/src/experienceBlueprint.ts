export type ExperiencePhase = {
  key: "X0" | "X1" | "X2" | "X3" | "X4" | "X5" | "X6";
  name: string;
  goal: string;
  dependsOn: string[];
};

export type FactoryZone = {
  key: string;
  label: string;
  shortLabel: string;
  purpose: string;
  sourceOfTruth: string[];
  phase: ExperiencePhase["key"];
  category: "CORE" | "RESEARCH" | "GOVERNANCE" | "PORTFOLIO" | "KNOWLEDGE" | "OPERATIONS";
};

export const EXPERIENCE_PHASES: ExperiencePhase[] = [
  { key: "X0", name: "Factory Blueprint", goal: "Define the canonical factory map, room contracts, navigation hierarchy, and truth bindings.", dependsOn: [] },
  { key: "X1", name: "Functional Command Center", goal: "Replace terminal babysitting with live system, job, agent, case, safety, and provider telemetry.", dependsOn: ["X0"] },
  { key: "X2", name: "Living Factory Floor", goal: "Animate real case and agent movement through the governed workflow without simulated activity.", dependsOn: ["X0", "X1"] },
  { key: "X3", name: "Art / Mob / Neon / MAX", goal: "Apply the cinematic visual identity, character system, humor, and MAX mascot to truthful live states.", dependsOn: ["X2"] },
  { key: "X4", name: "Judgment Bank Experience", goal: "Turn interviews, principles, dissent, and operator judgment into a navigable private intelligence library.", dependsOn: ["X1", "X3"] },
  { key: "X5", name: "Portfolio & Thesis War Room", goal: "Unify portfolio state, thesis integrity, catalysts, evidence deltas, risk, and paper outcomes in one room.", dependsOn: ["X1", "X2", "X4"] },
  { key: "X6", name: "Executive / Showcase Edition", goal: "Create the polished presentation layer for daily operation, demos, and executive review without hiding uncertainty.", dependsOn: ["X3", "X4", "X5"] },
];

export const FACTORY_ZONES: FactoryZone[] = [
  { key: "intelligence-floor", label: "Intelligence Floor", shortLabel: "Floor", purpose: "Global map of active cases, rooms, agents, and governed workflow state.", sourceOfTruth: ["/factory-room/status", "/monitoring/dashboard", "/agents"], phase: "X0", category: "CORE" },
  { key: "agent-desks", label: "Eight Specialist Desks", shortLabel: "Desks", purpose: "Policy, Macro, Fundamentals, Market Structure, Commodities, Geo/Weather, Skeptic, and Portfolio analysis.", sourceOfTruth: ["/agents", "agent_completion ledger objects"], phase: "X0", category: "CORE" },
  { key: "research-annex", label: "Research Annex", shortLabel: "Research", purpose: "External research intelligence such as Grok and Kimi, visually separated from native governed evidence.", sourceOfTruth: ["Grok experiment state", "Kimi research intelligence state", "source lineage"], phase: "X0", category: "RESEARCH" },
  { key: "committee-room", label: "Investment Committee Room", shortLabel: "Committee", purpose: "Synthesis, dissent, confidence, disposition, and decision lineage.", sourceOfTruth: ["committee_decision ledger objects", "/monitoring/dashboard"], phase: "X0", category: "GOVERNANCE" },
  { key: "skeptic-room", label: "Skeptic / Red Room", shortLabel: "Red Room", purpose: "Strongest counter-case, unresolved evidence, falsifiers, and thesis attack surface.", sourceOfTruth: ["skeptic agent outputs", "evidence gap state", "thesis falsifiers"], phase: "X0", category: "GOVERNANCE" },
  { key: "risk-inspection", label: "Risk Inspection", shortLabel: "Risk", purpose: "Deterministic risk rules and fail-closed safety gates.", sourceOfTruth: ["risk_inspection ledger objects", "/factory-room/status"], phase: "X0", category: "GOVERNANCE" },
  { key: "paper-execution", label: "Paper Execution Bay", shortLabel: "Paper Bay", purpose: "Paper-only authorization, sizing, execution lineage, and explicit live-capital lock state.", sourceOfTruth: ["paper authorization", "paper sizing", "paper execution ledger objects"], phase: "X0", category: "GOVERNANCE" },
  { key: "portfolio-office", label: "Portfolio Office", shortLabel: "Portfolio", purpose: "Paper portfolio positions, cash, concentration, exposures, outcomes, and portfolio-agent context.", sourceOfTruth: ["/factory-room/status portfolio", "paper portfolio ledger"], phase: "X5", category: "PORTFOLIO" },
  { key: "thesis-integrity", label: "Thesis Integrity Room", shortLabel: "Thesis", purpose: "Separate price performance from whether the original investment thesis remains intact, early, changed, or broken.", sourceOfTruth: ["thesis contract", "evidence delta", "re-underwrite lineage"], phase: "X5", category: "PORTFOLIO" },
  { key: "judgment-bank", label: "Judgment Bank / Interview Library", shortLabel: "Judgment Bank", purpose: "Professional interviews, principles, judgment cards, dissent, and learning history.", sourceOfTruth: ["/judgment-bank/scorecards/all", "interview portal", "judgment ledger"], phase: "X4", category: "KNOWLEDGE" },
  { key: "evidence-warehouse", label: "Evidence Warehouse", shortLabel: "Evidence", purpose: "Source lineage, freshness, hard data, filings, news, insider, institutional, macro, and policy evidence.", sourceOfTruth: ["evidence packets", "source lineage", "freshness guards"], phase: "X1", category: "KNOWLEDGE" },
  { key: "control-room", label: "Control Room", shortLabel: "Control", purpose: "System health, provider state, background jobs, schedules, experiments, version, and safety invariants.", sourceOfTruth: ["/system/status", "/factory-room/status", "job status endpoints"], phase: "X1", category: "OPERATIONS" },
];

export const EXPERIENCE_TRUTH_RULES = [
  "No animation may imply work unless a real backend state or ledger event supports it.",
  "Unknown data renders UNKNOWN or OFFLINE; it is never silently converted to READY.",
  "External research is visually distinct from native governed evidence.",
  "Paper/shadow state and live-capital lock remain visible in every execution-oriented view.",
  "Price performance is visually separated from thesis integrity.",
  "Humor and cinematic art may decorate state, but never replace uncertainty, source lineage, or safety information.",
] as const;
