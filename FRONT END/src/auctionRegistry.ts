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
  locked?: boolean;
};

export const AUCTION_ROOMS: readonly AuctionRoom[] = [
  { id: "radar", label: "Radar Room", shortLabel: "RADAR", deck: "upper", characterKeys: ["market_structure"], guests: [], source: "validation.layers.market_validation", purpose: "Receives only verified opportunity detections." },
  { id: "research", label: "Research Department", shortLabel: "RESEARCH", deck: "upper", characterKeys: ["fundamentals"], guests: [], source: "factory.cases / evidence receipts", purpose: "Assembles source-backed case evidence." },
  { id: "policy", label: "Policy Desk", shortLabel: "POLICY", deck: "upper", characterKeys: ["policy"], guests: [], source: "factory.desks.policy", purpose: "Interprets government and regulatory evidence." },
  { id: "macro", label: "Macro Desk", shortLabel: "MACRO", deck: "upper", characterKeys: ["macro", "commodities", "geo_weather"], guests: [], source: "factory.desks.macro / commodities / geo_weather", purpose: "Watches rates, physical markets, weather, and geopolitics." },
  { id: "external", label: "External Intelligence Annex", shortLabel: "EXT. INTEL", deck: "upper", characterKeys: [], guests: ["Grok", "Gemini", "Kimi"], source: "validation provider receipts", purpose: "Displays controlled external intelligence, never native fact." },
  { id: "committee", label: "Investment Committee Room", shortLabel: "COMMITTEE", deck: "main", characterKeys: ["policy", "portfolio"], guests: [], source: "committee decision receipts", purpose: "Presents governed deliberation and dissent." },
  { id: "skeptic", label: "Skeptic / Red Room", shortLabel: "RED ROOM", deck: "main", characterKeys: ["skeptic"], guests: [], source: "skeptic objections / falsifiers", purpose: "Attacks assumptions and preserves unresolved objections." },
  { id: "risk", label: "Risk Inspection", shortLabel: "RISK", deck: "main", characterKeys: ["skeptic", "portfolio"], guests: [], source: "risk inspection receipts", purpose: "Applies deterministic, fail-closed risk gates." },
  { id: "paper", label: "Paper Execution Bay", shortLabel: "PAPER BAY", deck: "main", characterKeys: ["portfolio"], guests: [], source: "paper decision receipts", purpose: "Shows simulation decisions only; no live capital authority.", locked: true },
  { id: "portfolio", label: "Portfolio Office", shortLabel: "PORTFOLIO", deck: "main", characterKeys: ["portfolio"], guests: [], source: "factory.paper_fund", purpose: "Shows sanitized paper NAV, cash, positions, and exposure." },
  { id: "monitoring", label: "Monitoring Floor", shortLabel: "MONITORING", deck: "lower", characterKeys: ["macro", "market_structure"], guests: [], source: "monitoring event receipts", purpose: "Observes outcomes without changing state." },
  { id: "learning", label: "Outcome Learning Lab", shortLabel: "LEARNING", deck: "lower", characterKeys: ["geo_weather"], guests: [], source: "validation.layers.outcome_learning", purpose: "Records labeled outcomes without rewriting history." },
  { id: "judgment", label: "Judgment Bank", shortLabel: "JUDGMENT", deck: "lower", characterKeys: ["policy"], guests: [], source: "judgment receipts", purpose: "Preserves lessons, dissent, and operator judgment." },
  { id: "evidence", label: "Evidence Warehouse", shortLabel: "EVIDENCE", deck: "lower", characterKeys: ["fundamentals", "commodities"], guests: [], source: "source lineage", purpose: "Holds provenance, timestamps, and evidence gaps." },
  { id: "thesis", label: "Thesis Integrity Room", shortLabel: "THESIS", deck: "lower", characterKeys: ["fundamentals", "skeptic"], guests: [], source: "thesis monitoring receipts", purpose: "Separates thesis integrity from price performance." },
  { id: "control", label: "Control Room", shortLabel: "CONTROL", deck: "lower", characterKeys: ["max"], guests: [], source: "availability / freshness / safety", purpose: "Displays health, provenance, and immutable authority locks." },
  { id: "replay", label: "Replay Theater", shortLabel: "REPLAY", deck: "lower", characterKeys: ["max"], guests: [], source: "historical=true receipts", purpose: "Reconstructs completed sessions only." },
  { id: "expansion", label: "Expansion Wing", shortLabel: "EXPANSION", deck: "lower", characterKeys: ["max"], guests: [], source: "static governed registry", purpose: "Shows proposed rooms without activating capability.", locked: true },
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
