import type { TruthRecord } from "./TruthSourceAdapter";

export type WallRoom = "radar" | "research" | "agents" | "committee" | "risk" | "paper" | "monitoring" | "learning" | "watch" | "idle";
export type Scene = {
  room: WallRoom;
  title: string;
  reason: string;
  narrative: string;
  unknowns: string;
  nextStep: string;
  character: string;
  camera: "wide" | "desk" | "chamber" | "inspection" | "watch";
  lighting: "gold" | "green" | "red" | "amber" | "quiet";
  animate: boolean;
  historical: boolean;
  receipt: TruthRecord;
};

function text(value: unknown, fallback = "UNKNOWN"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

export function mapEventToScene(event: TruthRecord | null, degraded = false): Scene {
  if (degraded) return scene("watch", "Factory Watch", "A source is stale, unavailable, conflicting, or incomplete.", "The Watch desk is comparing receipts before the floor moves.", "The affected source and downstream lineage remain unverified.", "Reconcile the source before accepting a new factory state.", "policy", "watch", "amber", false, event);
  if (!event || !text(event.event_type, "")) return scene("idle", "The House Is Quiet", "No current event with a complete receipt was supplied.", "The factory is reviewing incomplete evidence.", "There is no trustworthy current event to feature.", "Wait for a verified receipt; no operational movement is implied.", "max", "wide", "quiet", false, event);
  const type = text(event.event_type).toUpperCase();
  const receiptReady = Boolean(text(event.created_at, "") && (text(event.case_id, "") || text(event.entity_id, "")));
  const historical = Boolean(event.historical || event.presentation_only || event.replay);
  const mappings: Array<[RegExp, Omit<Scene, "receipt" | "animate" | "historical">]> = [
    [/OPPORTUNITY.*(DETECTED|FOUND)|OPPORTUNITY_DETECTED/, { room: "radar", title: "Opportunity detected", reason: "A sanitized intake receipt selected the Radar desk.", narrative: "The Radar desk has logged a candidate for governed review.", unknowns: "No case promotion is implied by intake alone.", nextStep: "Research may begin only when its own receipt arrives.", character: "market_structure", camera: "wide", lighting: "gold" }],
    [/OPPORTUNITY.*(PROMOTED|CASE)|CASE.*(OPENED|PROMOTED)/, { room: "research", title: "Opportunity promoted to case", reason: "A persisted promotion receipt selected the Research Annex.", narrative: "A candidate has a case receipt and enters evidence review.", unknowns: "The evidence record is not yet a conclusion.", nextStep: "Await the research or evidence receipt.", character: "fundamentals", camera: "desk", lighting: "green" }],
    [/RESEARCH|EVIDENCE|INGEST/, { room: "research", title: "Evidence received", reason: "A research receipt selected the evidence path.", narrative: "The Research Annex has received a source-backed item.", unknowns: "Agent interpretation remains a separate governed event.", nextStep: "Agents can review only the evidence that is actually attached.", character: "fundamentals", camera: "desk", lighting: "green" }],
    [/AGENT.*(COMPLETE|ANALYSIS)|ANALYSIS.*COMPLETE/, { room: "agents", title: "Agent analysis completed", reason: "A completed analysis receipt selected the Intelligence Floor.", narrative: "The eight desks have recorded an analysis receipt for review.", unknowns: "Consensus and committee action are not inferred.", nextStep: "Committee review requires its own completed receipt.", character: "skeptic", camera: "wide", lighting: "gold" }],
    [/COMMITTEE/, { room: "committee", title: "Committee completed", reason: "A committee receipt selected the Chamber.", narrative: "The Committee Chamber has a recorded deliberation outcome.", unknowns: "Risk inspection remains an independent gate.", nextStep: "Risk must complete before any paper decision is described.", character: "policy", camera: "chamber", lighting: "gold" }],
    [/RISK.*VETO|VETO/, { room: "risk", title: "Risk veto", reason: "A risk veto receipt selected Inspection.", narrative: "Inspection has withheld the file under the recorded risk gate.", unknowns: "No paper action follows from a veto.", nextStep: "Preserve the receipt and await a new governed decision.", character: "skeptic", camera: "inspection", lighting: "red" }],
    [/RISK/, { room: "risk", title: "Risk inspection completed", reason: "A risk receipt selected Inspection.", narrative: "Inspection has recorded its gate result.", unknowns: "Paper activity is not inferred from inspection alone.", nextStep: "Look for a separate paper decision receipt.", character: "skeptic", camera: "inspection", lighting: "amber" }],
    [/PAPER.*DECISION|PAPER|ORDER/, { room: "paper", title: "Paper decision recorded", reason: "A paper receipt selected the Operations Bay.", narrative: "Paper Operations has recorded a read-only decision receipt.", unknowns: "No live execution or ledger authority exists here.", nextStep: "Monitoring can report only a later verified update.", character: "portfolio", camera: "desk", lighting: "green" }],
    [/MONITOR|THESIS/, { room: "monitoring", title: "Monitoring update", reason: "A monitoring receipt selected Factory Watch.", narrative: "Monitoring has posted a verified update for the watch floor.", unknowns: "Outcome and learning remain separate events.", nextStep: "Continue observation until a new receipt is supplied.", character: "macro", camera: "watch", lighting: "green" }],
    [/OUTCOME|LEARNING|JUDGMENT/, { room: "learning", title: "Learning update", reason: "An outcome receipt selected the Judgment Archive.", narrative: "The Archive has received a labeled outcome or judgment update.", unknowns: "The label does not rewrite earlier receipts.", nextStep: "Retain the outcome as historical evidence.", character: "geo_weather", camera: "desk", lighting: "gold" }],
  ];
  const match = mappings.find(([pattern]) => pattern.test(type));
  const base = match?.[1] ?? { room: "radar", title: type.replaceAll("_", " "), reason: "An unclassified event selected the intake desk.", narrative: "The factory received an event without a known scene mapping.", unknowns: "Its downstream meaning is unknown.", nextStep: "Open the receipt before assigning a governed stage.", character: "max", camera: "wide", lighting: "amber" };
  const complete = receiptReady && !/INCOMPLETE|MISSING_LINEAGE/.test(type);
  return { ...base, animate: complete, historical, receipt: event, reason: complete ? base.reason : "Event lineage is incomplete; movement is withheld." };
}

function scene(room: WallRoom, title: string, reason: string, narrative: string, unknowns: string, nextStep: string, character: string, camera: Scene["camera"], lighting: Scene["lighting"], animate: boolean, receipt: TruthRecord | null): Scene {
  return { room, title, reason, narrative, unknowns, nextStep, character, camera, lighting, animate, historical: false, receipt: receipt ?? {} };
}

export function maxNarration(scene: Scene): string {
  return scene.narrative;
}