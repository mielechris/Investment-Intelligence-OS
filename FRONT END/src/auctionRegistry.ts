import type { LivingCastKey } from "./livingCast";

export type RoomState = "idle" | "active" | "degraded" | "unavailable" | "locked";
export type AuctionRoomId =
  | "radar" | "research" | "policy" | "macro" | "external" | "committee"
  | "skeptic" | "risk" | "paper" | "portfolio" | "monitoring" | "learning"
  | "judgment" | "evidence" | "thesis" | "control" | "replay" | "expansion";

export type AuctionRoom = {
  id: AuctionRoomId;
  label: string;
  shortLabel: string;
  deck: "upper" | "main" | "lower";
  characterKeys: LivingCastKey[];
  guests: string[];
  source: string;
  purpose: string;
  silhouette: string;
  instruments: readonly string[];
  light: string;
  idleBehavior: string;
  locked?: boolean;
};

export const AUCTION_ROOMS: readonly AuctionRoom[] = [
  { id: "radar", label: "Radar Room", shortLabel: "RADAR", deck: "upper", characterKeys: ["market_structure"], guests: [], source: "validation.layers.market_validation", purpose: "Receives only verified opportunity detections.", silhouette: "circular sweep theater", instruments: ["sector scope", "receipt beacon", "signal rail"], light: "muted teal phosphor", idleBehavior: "scope sweep without signal creation" },
  { id: "research", label: "Research Department", shortLabel: "RESEARCH", deck: "upper", characterKeys: ["fundamentals"], guests: [], source: "factory.cases / evidence receipts", purpose: "Assembles source-backed case evidence.", silhouette: "tiered archive library", instruments: ["document table", "source drawers", "reading lamps"], light: "parchment task light", idleBehavior: "reading lamps breathe over empty files" },
  { id: "policy", label: "Policy Desk", shortLabel: "POLICY", deck: "upper", characterKeys: ["policy"], guests: [], source: "factory.desks.policy", purpose: "Interprets government and regulatory evidence.", silhouette: "marble briefing alcove", instruments: ["statute folios", "jurisdiction map", "date clock"], light: "institutional amber", idleBehavior: "clock advances; folios remain closed" },
  { id: "macro", label: "Macro Desk", shortLabel: "MACRO", deck: "upper", characterKeys: ["macro", "commodities", "geo_weather"], guests: [], source: "factory.desks.macro / commodities / geo_weather", purpose: "Watches rates, physical markets, weather, and geopolitics.", silhouette: "three-bay observatory", instruments: ["yield wall", "weather globe", "commodity gauges"], light: "storm bronze", idleBehavior: "gauges hold their last observed positions" },
  { id: "external", label: "External Intelligence Annex", shortLabel: "EXT. INTEL", deck: "upper", characterKeys: [], guests: ["Grok", "Gemini", "Kimi"], source: "validation provider receipts", purpose: "Displays controlled external intelligence, never native fact.", silhouette: "quarantined glass annex", instruments: ["provider booths", "provenance hatch", "isolation shutters"], light: "cool quarantine teal", idleBehavior: "shutters remain half-drawn" },
  { id: "committee", label: "Investment Committee Room", shortLabel: "COMMITTEE", deck: "main", characterKeys: ["policy", "portfolio"], guests: [], source: "committee decision receipts", purpose: "Presents governed deliberation and dissent.", silhouette: "oval deliberation chamber", instruments: ["horseshoe table", "dissent lamps", "decision seal"], light: "tobacco chandelier", idleBehavior: "empty chairs hold deliberate symmetry" },
  { id: "skeptic", label: "Skeptic / Red Room", shortLabel: "RED ROOM", deck: "main", characterKeys: ["skeptic"], guests: [], source: "skeptic objections / falsifiers", purpose: "Attacks assumptions and preserves unresolved objections.", silhouette: "compressed adversarial bunker", instruments: ["falsifier wall", "cross-examination lamp", "red dossier press"], light: "restrained oxblood", idleBehavior: "warning lamp smolders without alarm" },
  { id: "risk", label: "Risk Inspection", shortLabel: "RISK", deck: "main", characterKeys: ["skeptic", "portfolio"], guests: [], source: "risk inspection receipts", purpose: "Applies deterministic, fail-closed risk gates.", silhouette: "steel inspection gantry", instruments: ["limit gauges", "veto gate", "exposure scale"], light: "cold inspection blue", idleBehavior: "gauges rest at fail-closed zero" },
  { id: "paper", label: "Paper Execution Bay", shortLabel: "PAPER BAY", deck: "main", characterKeys: ["portfolio"], guests: [], source: "paper decision receipts", purpose: "Shows simulation decisions only; no live capital authority.", silhouette: "sealed simulation bay", instruments: ["paper ticket press", "sandbox rail", "authority lock"], light: "locked brass", idleBehavior: "press remains mechanically isolated", locked: true },
  { id: "portfolio", label: "Portfolio Office", shortLabel: "PORTFOLIO", deck: "main", characterKeys: ["portfolio"], guests: [], source: "factory.paper_fund", purpose: "Shows sanitized paper NAV, cash, positions, and exposure.", silhouette: "walnut stewardship office", instruments: ["paper ledger", "exposure abacus", "position cabinet"], light: "banker-lamp green", idleBehavior: "ledger stays closed between receipts" },
  { id: "monitoring", label: "Monitoring Floor", shortLabel: "MONITORING", deck: "lower", characterKeys: ["macro", "market_structure"], guests: [], source: "monitoring event receipts", purpose: "Observes outcomes without changing state.", silhouette: "long watch gallery", instruments: ["cadence clocks", "observation scopes", "outcome rail"], light: "night-watch teal", idleBehavior: "clocks and fans continue at low cadence" },
  { id: "learning", label: "Outcome Learning Lab", shortLabel: "LEARNING", deck: "lower", characterKeys: ["geo_weather"], guests: [], source: "validation.layers.outcome_learning", purpose: "Records labeled outcomes without rewriting history.", silhouette: "stepped specimen laboratory", instruments: ["outcome trays", "label press", "memory reels"], light: "faded laboratory amber", idleBehavior: "empty reels turn without recording" },
  { id: "judgment", label: "Judgment Bank", shortLabel: "JUDGMENT", deck: "lower", characterKeys: ["policy"], guests: [], source: "judgment receipts", purpose: "Preserves lessons, dissent, and operator judgment.", silhouette: "vaulted memory bank", instruments: ["judgment drawers", "dissent ledger", "sealed minutes"], light: "aged parchment", idleBehavior: "vault indicators hold steady" },
  { id: "evidence", label: "Evidence Warehouse", shortLabel: "EVIDENCE", deck: "lower", characterKeys: ["fundamentals", "commodities"], guests: [], source: "source lineage", purpose: "Holds provenance, timestamps, and evidence gaps.", silhouette: "double-height provenance stacks", instruments: ["lineage crane", "source pallets", "gap markers"], light: "warehouse sodium", idleBehavior: "empty crane idles over the receiving rail" },
  { id: "thesis", label: "Thesis Integrity Room", shortLabel: "THESIS", deck: "lower", characterKeys: ["fundamentals", "skeptic"], guests: [], source: "thesis monitoring receipts", purpose: "Separates thesis integrity from price performance.", silhouette: "balanced examination chamber", instruments: ["claim spine", "falsifier balance", "drift gauge"], light: "split amber and oxblood", idleBehavior: "balance remains level until evidence arrives" },
  { id: "control", label: "Control Room", shortLabel: "CONTROL", deck: "lower", characterKeys: ["max"], guests: [], source: "availability / freshness / safety", purpose: "Displays health, provenance, and immutable authority locks.", silhouette: "armored governance core", instruments: ["safety annunciator", "freshness clock", "authority keys"], light: "low control-room green", idleBehavior: "locks remain visibly engaged" },
  { id: "replay", label: "Replay Theater", shortLabel: "REPLAY", deck: "lower", characterKeys: ["max"], guests: [], source: "historical=true receipts", purpose: "Reconstructs completed sessions only.", silhouette: "screening room with film bays", instruments: ["historical projector", "receipt filmstrip", "current-state shutter"], light: "projector parchment", idleBehavior: "blank screen and stopped reels" },
  { id: "expansion", label: "Expansion Wing", shortLabel: "EXPANSION", deck: "lower", characterKeys: ["max"], guests: [], source: "static governed registry", purpose: "Shows proposed rooms without activating capability.", silhouette: "bricked and scaffolded wing", instruments: ["sealed doorway", "registry plaque", "inactive conduit"], light: "worklight behind shutters", idleBehavior: "all conduits remain disconnected", locked: true },
] as const;

export const EVENT_ROOM: Readonly<Record<string, AuctionRoomId>> = {
  opportunity_detected: "radar",
  opportunity_promoted_to_case: "research",
  research_evidence_received: "research",
  policy_analysis_completed: "policy",
  macro_analysis_completed: "macro",
  external_intelligence_received: "external",
  agent_analysis_completed: "research",
  committee_completed: "committee",
  skeptic_challenge_recorded: "skeptic",
  risk_inspection_completed: "risk",
  risk_veto: "risk",
  paper_decision_recorded: "paper",
  portfolio_updated: "portfolio",
  monitoring_update: "monitoring",
  learning_outcome_update: "learning",
  judgment_recorded: "judgment",
  evidence_archived: "evidence",
  thesis_status_updated: "thesis",
} as const;

export const AUCTION_CHARACTERS = [
  { key: "max", room: "control", role: "Factory foreman" },
  { key: "policy", room: "policy", role: "Policy evidence" },
  { key: "macro", room: "macro", role: "Rates and regimes" },
  { key: "fundamentals", room: "research", role: "Case research" },
  { key: "market_structure", room: "radar", role: "Market radar" },
  { key: "commodities", room: "macro", role: "Physical markets" },
  { key: "geo_weather", room: "macro", role: "Geopolitics and weather" },
  { key: "skeptic", room: "skeptic", role: "Adversarial review" },
  { key: "portfolio", room: "portfolio", role: "Paper portfolio context" },
] as const;
