import { AUCTION_ROOMS, EVENT_ROOM, type AuctionRoomId, type RoomState } from "./auctionRegistry.ts";
import type { TruthRecord, TruthResult } from "./TruthSourceAdapter";

export type GovernedEvent = { id: string; type: string; room: AuctionRoomId | null; at: string; caseId: string | null; historical: boolean; provenance: string; animate: boolean };
export type GovernedCase = { id: string; ticker: string; thesis: string; evidenceFor: string; evidenceAgainst: string; committee: string; risk: string; paper: string; monitoring: string; drift: string; learned: string; provenance: string };
export type AuctionModel = {
  condition: "AVAILABLE" | "STALE" | "SOURCE_CONFLICT" | "UNAVAILABLE";
  freshness: "CURRENT" | "STALE" | "UNAVAILABLE";
  generatedAt: string | null;
  quiet: boolean;
  safety: { telemetryReadOnly: boolean; ledger: boolean; write: boolean; trade: boolean; live: boolean };
  nav: number | null;
  marketValidation: string;
  rooms: Record<AuctionRoomId, RoomState>;
  events: GovernedEvent[];
  replay: GovernedEvent[];
  cases: GovernedCase[];
  activeRoom: AuctionRoomId | null;
  lighting: "day" | "market-open" | "market-close" | "night";
};

const record = (value: unknown): TruthRecord => value !== null && typeof value === "object" && !Array.isArray(value) ? value as TruthRecord : {};
const rows = (value: unknown): TruthRecord[] => Array.isArray(value) ? value.filter((item): item is TruthRecord => item !== null && typeof item === "object" && !Array.isArray(item)) : [];
const text = (value: unknown, fallback = "UNKNOWN") => typeof value === "string" && value.trim() ? value.trim() : fallback;
const maybeText = (value: unknown) => typeof value === "string" && value.trim() ? value.trim() : null;

function lightingFor(date: Date): AuctionModel["lighting"] {
  const hour = date.getHours();
  if (hour < 7 || hour >= 20) return "night";
  if (hour < 10) return "market-open";
  if (hour >= 15) return "market-close";
  return "day";
}

export function normalizeEvent(value: TruthRecord): GovernedEvent | null {
  const type = maybeText(value.event_type)?.toLowerCase();
  const at = maybeText(value.created_at ?? value.timestamp);
  const lineage = maybeText(value.case_id ?? value.entity_id);
  if (!type || !at || Number.isNaN(Date.parse(at)) || !lineage) return null;
  const room = EVENT_ROOM[type] ?? null;
  return {
    id: text(value.event_id ?? value.id, `${type}:${at}:${lineage}`),
    type,
    room,
    at,
    caseId: maybeText(value.case_id),
    historical: value.historical === true || value.presentation_only === true || value.replay === true,
    provenance: text(value.source_identity ?? value.source ?? value.receipt_id, "SOURCE RECEIPT PRESENT; ID UNKNOWN"),
    animate: room !== null,
  };
}

function normalizeCase(value: TruthRecord): GovernedCase | null {
  const id = maybeText(value.case_id);
  if (!id) return null;
  return {
    id,
    ticker: text(value.ticker), thesis: text(value.thesis ?? value.topic),
    evidenceFor: text(value.supporting_evidence), evidenceAgainst: text(value.opposing_evidence),
    committee: text(value.committee_outcome ?? value.committee_disposition), risk: text(value.risk_inspection ?? value.risk_decision),
    paper: text(value.paper_decision), monitoring: text(value.monitoring_status), drift: text(value.thesis_drift),
    learned: text(value.learned_outcome), provenance: text(value.source_identity ?? value.receipt_id),
  };
}

export function buildAuctionModel(result: TruthResult | null, error: string | null, now = new Date()): AuctionModel {
  const data = record(result?.data);
  const freshnessRecord = record(data.freshness);
  const safetyRecord = record(data.safety);
  const factory = record(data.factory);
  const layers = record(record(data.validation).layers);
  const telemetryPayload = record(record(layers.factory_telemetry).payload);
  const factoryPayload = record(factory.payload);
  const payload = Object.keys(factoryPayload).length ? factoryPayload : telemetryPayload;
  const condition = error || !result ? "UNAVAILABLE" : (["AVAILABLE", "STALE", "SOURCE_CONFLICT", "UNAVAILABLE"].includes(String(data.availability)) ? data.availability as AuctionModel["condition"] : "UNAVAILABLE");
  const freshness = ["CURRENT", "STALE", "UNAVAILABLE"].includes(String(freshnessRecord.state)) ? freshnessRecord.state as AuctionModel["freshness"] : "UNAVAILABLE";
  const safe = safetyRecord.telemetry_read_only === true && safetyRecord.direct_ledger_access === false && safetyRecord.backend_write_permission === false && safetyRecord.trade_execution_permission === false && safetyRecord.live_execution === false;
  const events = rows(payload.recent_meaningful_events ?? payload.recent_events ?? payload.events).map(normalizeEvent).filter((item): item is GovernedEvent => item !== null);
  const cases = rows(payload.cases).map(normalizeCase).filter((item): item is GovernedCase => item !== null);
  const healthy = condition === "AVAILABLE" && freshness === "CURRENT" && safe && data.source_conflict !== true;
  const active = healthy ? events.find((event) => !event.historical && event.room !== null) ?? null : null;
  const rooms = Object.fromEntries(AUCTION_ROOMS.map((room) => [room.id, room.locked ? "locked" : healthy ? active?.room === room.id ? "active" : "idle" : condition === "UNAVAILABLE" ? "unavailable" : "degraded"])) as Record<AuctionRoomId, RoomState>;
  const paperFund = record(factory.paper_fund ?? record(payload.portfolio));
  return {
    condition, freshness, generatedAt: maybeText(data.generated_at), quiet: !active,
    safety: { telemetryReadOnly: safetyRecord.telemetry_read_only === true, ledger: safetyRecord.direct_ledger_access === true, write: safetyRecord.backend_write_permission === true, trade: safetyRecord.trade_execution_permission === true, live: safetyRecord.live_execution === true },
    nav: typeof paperFund.nav === "number" && Number.isFinite(paperFund.nav) ? paperFund.nav : null,
    marketValidation: text(record(layers.market_validation).availability), rooms, events,
    replay: events.filter((event) => event.historical), cases, activeRoom: active?.room ?? null, lighting: lightingFor(now),
  };
}
