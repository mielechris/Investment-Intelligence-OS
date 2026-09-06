import type { ExpansionSnapshot } from "./ExpansionWingSnapshotContext";
import type { AuctionRoomId } from "./auctionRegistry";

type Dict = Record<string, unknown>;
export type MuseumOutput = { state: string; value: string; source: string; timestamp: string | null; freshness: string; nextObservation: string | null; count: number | null; blocker: string | null; eventCategory: string | null };
export type FactoryOutputReceipt = { id: string; timestamp: string; module: string; category: string; state: string; opaqueIdentity: string | null; freshness: string; explanation: string };
export type CaseReceiptLink = { receipt: FactoryOutputReceipt; caseId: string | null; state: "LINKED" | "UNLINKED"; reason: string };
const dict = (value: unknown): Dict => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Dict : {};
const list = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const scalar = (value: unknown): string | null => typeof value === "string" && value.trim() ? value.trim() : typeof value === "number" && Number.isFinite(value) ? String(value) : typeof value === "boolean" ? String(value).toUpperCase() : null;
const path = (root: unknown, ...keys: string[]): unknown => keys.reduce((value, key) => dict(value)[key], root);
const section = (snapshot: ExpansionSnapshot | null, name: string) => snapshot?.sections?.[name] ?? null;
const sectionData = (snapshot: ExpansionSnapshot | null, name: string) => dict(section(snapshot, name)?.data);
const timeFrom = (data: Dict): string | null => scalar(data.generated_at ?? data.observed_at ?? data.source_generated_at ?? data.projection_generated_at ?? data.last_publication_time ?? data.last_cycle_completed_at ?? data.snapshot_as_of);
const status = (state: unknown): string => scalar(state) ?? "UNAVAILABLE";
const unavailable = (source: string, state = "UNAVAILABLE", blocker = "AUTHENTICATED_FIELD_NOT_REPORTED"): MuseumOutput => ({ state, value: "Authenticated source did not report this field", source, timestamp: null, freshness: state, nextObservation: null, count: null, blocker, eventCategory: null });
const output = (source: string, stateValue: unknown, value: unknown, options: Partial<MuseumOutput> = {}): MuseumOutput => {
  const state = status(stateValue); const rendered = scalar(value);
  if (rendered === null) return unavailable(source, state, state === "UNAVAILABLE" ? "SANITIZED_SOURCE_UNAVAILABLE" : "AUTHENTICATED_FIELD_NOT_REPORTED");
  return { state, value: rendered, source, timestamp: null, freshness: state, nextObservation: null, count: null, blocker: ["CURRENT", "AVAILABLE", "AVAILABLE_EMPTY"].includes(state) ? null : state, eventCategory: null, ...options };
};

function cadence(overview: unknown, key: "observation" | "paper_trading" | "radar"): Dict { return dict(path(overview, "validation", "layers", "factory_telemetry", "payload", "cadence", key)); }
function paper(overview: unknown): Dict { return dict(path(overview, "validation", "layers", "factory_telemetry", "payload", "paper_fund")); }
function telemetryRadar(overview: unknown): Dict { return dict(path(overview, "validation", "layers", "factory_telemetry", "payload", "radar")); }

export function stationOutput(id: string, snapshot: ExpansionSnapshot | null, overview: unknown): MuseumOutput {
  const books = sectionData(snapshot, "books"), radar = sectionData(snapshot, "radar"), projection = sectionData(snapshot, "projection_activation"), tuesday = sectionData(snapshot, "tuesday_command_center");
  const map: Record<string, () => MuseumOutput> = {
    executive: () => output("/living/overview · factory", path(overview, "factory", "availability"), path(overview, "validation", "layers", "factory_telemetry", "payload", "health", "state"), { timestamp: scalar(path(overview, "generated_at")), freshness: status(path(overview, "cache", "freshness_state")) }),
    calendar: () => output("/expansion-wing/snapshot · market_session", section(snapshot, "market_session")?.state, sectionData(snapshot, "market_session").state, { timestamp: timeFrom(sectionData(snapshot, "market_session")) }),
    services: () => output("/expansion-wing/snapshot · service_health", section(snapshot, "service_health")?.state, sectionData(snapshot, "service_health").backend_reachable, { timestamp: scalar(path(overview, "generated_at")) }),
    cadence: () => { const a=cadence(overview,"observation"), b=cadence(overview,"paper_trading"), e=cadence(overview,"radar"); return output("/living/overview · cadence", "CURRENT", `9A ${status(a.cadence_state)} · 9B ${status(b.cadence_state)} · 9E ${status(e.cadence_state)}`, { timestamp: scalar(a.last_completed_at), nextObservation: scalar(e.next_due_at) }); },
    pipeline: () => { const a=cadence(overview,"observation"), b=cadence(overview,"paper_trading"), e=cadence(overview,"radar"); return output("/living/overview · cadence", section(snapshot,"radar")?.state, `9A ${status(a.availability)} · 9B ${status(b.availability)} · 9E ${status(e.availability)}`, { timestamp: scalar(e.last_completed_at), nextObservation: scalar(e.next_due_at) }); },
    validation: () => output("/expansion-wing/snapshot · benchmark_9h", section(snapshot,"benchmark_9h")?.state, sectionData(snapshot,"benchmark_9h").status, { count: typeof sectionData(snapshot,"benchmark_9h").opportunity_count === "number" ? sectionData(snapshot,"benchmark_9h").opportunity_count as number : null }),
    shadow: () => output("/expansion-wing/snapshot · shadow_9i", section(snapshot,"shadow_9i")?.state, sectionData(snapshot,"shadow_9i").status),
    outcomes: () => output("/expansion-wing/snapshot · outcomes_9j", section(snapshot,"outcomes_9j")?.state, sectionData(snapshot,"outcomes_9j").status, { count: typeof sectionData(snapshot,"outcomes_9j").outcome_count === "number" ? sectionData(snapshot,"outcomes_9j").outcome_count as number : null }),
    radar: () => output("/expansion-wing/snapshot · radar", section(snapshot,"radar")?.state, radar.governed_universe_count, { timestamp: scalar(telemetryRadar(overview).last_cycle_completed_at), count: typeof radar.governed_universe_count === "number" ? radar.governed_universe_count : null, eventCategory: "RADAR_CYCLE" }),
    lineage: () => output("/expansion-wing/snapshot · radar", section(snapshot,"radar")?.state, radar.candidate_lineage_state),
    external: () => output("/expansion-wing/snapshot · primary_source_review_queue", section(snapshot,"primary_source_review_queue")?.state, sectionData(snapshot,"primary_source_review_queue").queue_count, { count: typeof sectionData(snapshot,"primary_source_review_queue").queue_count === "number" ? sectionData(snapshot,"primary_source_review_queue").queue_count as number : null }),
    conveyor: () => output("/expansion-wing/snapshot · candidate_conveyor", section(snapshot,"candidate_conveyor")?.state, `${list(sectionData(snapshot,"candidate_conveyor").candidates).length} authenticated identities`, { count: list(sectionData(snapshot,"candidate_conveyor").candidates).length, eventCategory: "CANDIDATE_LINEAGE" }),
    committee: () => unavailable("/expansion-wing/snapshot · committee", status(section(snapshot,"committee")?.state)),
    skeptic: () => unavailable("/expansion-wing/snapshot · risk", status(section(snapshot,"risk")?.state)),
    risk: () => unavailable("/expansion-wing/snapshot · risk", status(section(snapshot,"risk")?.state)),
    paper: () => section(snapshot,"books") ? output("/expansion-wing/snapshot · books", section(snapshot,"books")?.state, `NAV ${scalar(books.nav) ?? "UNAVAILABLE"} · CASH ${scalar(books.cash) ?? "UNAVAILABLE"} · POS ${scalar(books.positions) ?? "UNAVAILABLE"} · TX ${scalar(books.transactions) ?? "UNAVAILABLE"} · ORD ${scalar(books.orders) ?? "UNAVAILABLE"} · FILL ${scalar(books.fills) ?? "UNAVAILABLE"}`, { timestamp: scalar(paper(overview).snapshot_as_of) }) : unavailable("/expansion-wing/snapshot · books", "UNAVAILABLE", "SANITIZED_SOURCE_UNAVAILABLE"),
    reader: () => output("/expansion-wing/snapshot · projection_activation", section(snapshot,"projection_activation")?.state, `${status(projection.reader_state)} · INTEGRITY ${status(projection.integrity_state)} · HASH ${status(projection.hash_validation)}`, { timestamp: timeFrom(projection), freshness: status(projection.freshness_state ?? projection.freshness) }),
    publisher: () => output("/expansion-wing/snapshot · projection_activation", section(snapshot,"projection_activation")?.state, `SEQUENCE ${scalar(projection.sequence) ?? "UNAVAILABLE"} · PUBLISHER ${status(projection.publisher_state)}`, { timestamp: timeFrom(projection), eventCategory: "PROJECTION_OBSERVATION" }),
    provider: () => output("/expansion-wing/snapshot · provider_credit_meter", section(snapshot,"provider_credit_meter")?.state, sectionData(snapshot,"provider_credit_meter").state),
    professional: () => output("/expansion-wing/snapshot · professional_strategy_observatory", section(snapshot,"professional_strategy_observatory")?.state, sectionData(snapshot,"professional_strategy_observatory").state),
    products: () => output("/expansion-wing/snapshot · tuesday_command_center", section(snapshot,"tuesday_command_center")?.state, `${scalar(path(tuesday,"product_summary","current")) ?? "UNAVAILABLE"} current / ${scalar(path(tuesday,"product_summary","total")) ?? "UNAVAILABLE"} registered`, { count: typeof path(tuesday,"product_summary","total") === "number" ? path(tuesday,"product_summary","total") as number : null }),
    methods: () => output("/expansion-wing/snapshot · tuesday_command_center", section(snapshot,"method_manager_scoreboard")?.state, `${scalar(path(tuesday,"method_summary","rankable")) ?? "UNAVAILABLE"} rankable / ${scalar(path(tuesday,"method_summary","total")) ?? "UNAVAILABLE"} registered`, { count: typeof path(tuesday,"method_summary","total") === "number" ? path(tuesday,"method_summary","total") as number : null }),
    sleeves: () => output("/expansion-wing/snapshot · tuesday_command_center", section(snapshot,"paper_research_sleeves")?.state, `${scalar(path(tuesday,"sleeves","product_count")) ?? "UNAVAILABLE"} synthetic sleeves · operational positions ${scalar(path(tuesday,"sleeves","operational_positions_created")) ?? "UNAVAILABLE"}`),
    warehouse: () => unavailable("/expansion-wing/snapshot · evidence metadata", "UNAVAILABLE"),
    receipts: () => output("/living/overview · recent_meaningful_events", "CURRENT", `${latestFactoryOutputs(overview, 8).length} bounded sanitized outputs`, { count: latestFactoryOutputs(overview,8).length }),
    postclose: () => unavailable("/expansion-wing/snapshot · post_close_control", status(section(snapshot,"post_close_control")?.state)),
    security: () => output("/expansion-wing/snapshot · authority_lock", section(snapshot,"authority_lock")?.state, Object.entries(sectionData(snapshot,"authority_lock")).filter(([key]) => key !== "locked").every(([,value]) => value === false) ? "ALL PROHIBITED AUTHORITY FALSE" : "AUTHORITY CONFLICT"),
    blockers: () => output("/expansion-wing/snapshot · tuesday_command_center", section(snapshot,"tuesday_command_center")?.state, `${list(tuesday.blockers).length} authenticated blocker categories`, { count: list(tuesday.blockers).length, nextObservation: scalar(path(tuesday,"session_gates","PRE_MARKET")) }),
  };
  return map[id]?.() ?? unavailable("SANITIZED SOURCE");
}

const ROOM_STATION: Record<AuctionRoomId,string> = { radar:"radar",research:"external",policy:"external",macro:"products",external:"external",committee:"committee",skeptic:"skeptic",risk:"risk",paper:"paper",portfolio:"paper",monitoring:"cadence",learning:"outcomes",judgment:"professional",evidence:"receipts",thesis:"validation",control:"executive",replay:"receipts",expansion:"products" };
export function roomOutput(room: AuctionRoomId, snapshot: ExpansionSnapshot | null, overview: unknown): MuseumOutput { return stationOutput(ROOM_STATION[room], snapshot, overview); }

const ALLOWED_EVENTS = new Set(["RISK_COMPLETE","COMMITTEE_COMPLETE","OPPORTUNITY_PROMOTED_TO_CASE","PAPER_PORTFOLIO_TRANSACTION_INGESTED","MONITORING_UPDATE","LEARNING_OUTCOME_UPDATE","JUDGMENT_RECORDED","EVIDENCE_ARCHIVED","THESIS_STATUS_UPDATED"]);
export function latestFactoryOutputs(overview: unknown, limit = 8): FactoryOutputReceipt[] {
  const rows = list(path(overview,"validation","layers","factory_telemetry","payload","recent_meaningful_events")); const seen = new Set<string>(); const out: FactoryOutputReceipt[] = [];
  for (const item of rows) { const row=dict(item), category=scalar(row.event_type), timestamp=scalar(row.created_at ?? row.timestamp); if (!category || !timestamp || !ALLOWED_EVENTS.has(category)) continue; const identity=scalar(row.case_id ?? row.cycle_id); const key=`${category}:${timestamp}:${identity ?? "NONE"}`; if(seen.has(key)) continue; seen.add(key); out.push({id:key,timestamp,module:category.startsWith("RISK")?"RISK":category.startsWith("COMMITTEE")?"COMMITTEE":category.startsWith("OPPORTUNITY")?"RADAR":"FACTORY",category,state:"AUTHENTICATED_RECEIPT",opaqueIdentity:identity,freshness:"HISTORICAL_RECEIPT",explanation:category === "OPPORTUNITY_PROMOTED_TO_CASE" ? "A governed historical promotion receipt was recorded; it is not a current candidate." : "A bounded sanitized factory receipt was recorded."}); if(out.length>=Math.max(0,Math.min(limit,8))) break; }
  return out;
}

export function linkPromotionReceipts(receipts: FactoryOutputReceipt[], cases: unknown): CaseReceiptLink[] {
  const ids = new Set(list(cases).map((item) => scalar(dict(item).case_id)).filter((item): item is string => item !== null));
  return receipts.filter((receipt) => receipt.category === "OPPORTUNITY_PROMOTED_TO_CASE").map((receipt) => {
    if (receipt.opaqueIdentity === null) return { receipt, caseId: null, state: "UNLINKED", reason: "NO_BROWSER_SAFE_CASE_IDENTITY" };
    if (!ids.has(receipt.opaqueIdentity)) return { receipt, caseId: null, state: "UNLINKED", reason: "IDENTITY_NOT_PRESENT_IN_AUTHENTICATED_REGISTRY" };
    return { receipt, caseId: receipt.opaqueIdentity, state: "LINKED", reason: "EXACT_IMMUTABLE_CASE_IDENTITY" };
  });
}
