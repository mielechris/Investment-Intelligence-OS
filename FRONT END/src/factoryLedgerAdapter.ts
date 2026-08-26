import type { FactoryZoneKey } from "./factoryGeometry";
import type { FactoryEvent, FactoryEventType } from "./factoryMovement";

export type RawLedgerEvent = {
  event_id?: string;
  case_id?: string;
  event_type?: string;
  created_at?: string;
  room?: string;
  payload?: Record<string, unknown>;
};

export type AdaptedLedgerEvent = {
  raw: RawLedgerEvent;
  canonical: FactoryEvent | null;
  zone: FactoryZoneKey | null;
  reason: string | null;
};

const ROOM_MAP: Record<string, FactoryZoneKey> = {
  EVIDENCE: "evidence-warehouse",
  EIGHT_DESKS: "agent-desks",
  COMMITTEE: "committee-room",
  RISK: "risk-inspection",
  PAPER_PORTFOLIO: "paper-execution",
};

function canonicalType(rawType: string): FactoryEventType | null {
  const event = rawType.toUpperCase();

  if (event.includes("CASE_CREATED")) return "case.created";
  if (event.includes("EVIDENCE") || event.includes("INGEST") || event.includes("PRIMARY_")) return "evidence.loaded";
  if (event.includes("AGENT_COMPLETE") || event.includes("SPECIALIST_COMPLETE") || event.includes("DESK_COMPLETE")) return "agent.completed";
  if (event.includes("AGENT_START") || event.includes("SPECIALIST_START") || event.includes("DESK_START")) return "agent.assigned";
  if (event.includes("COMMITTEE_COMPLETE")) return "committee.completed";
  if (event.includes("COMMITTEE")) return "committee.opened";
  if (event.includes("RISK_REJECT") || event.includes("RISK_DENY")) return "risk.rejected";
  if (event.includes("RISK_COMPLETE") || event.includes("RISK_CLEAR") || event.includes("RISK_AUTH")) return "risk.cleared";
  if (event.includes("RISK_")) return "risk.inspected";
  if (event.includes("PAPER_ORDER") && (event.includes("FILLED") || event.includes("EXECUTED"))) return "paper.order.filled";
  if (event.includes("PAPER_ORDER")) return "paper.order.created";
  if (event.includes("PAPER_EXECUTION") || event.includes("AUTHORIZATION")) return "execution.approved";
  if (event.includes("THESIS") && event.includes("BROKEN")) return "thesis.status_changed";
  if (event.includes("THESIS") || event.includes("MONITOR")) return "thesis.monitored";
  if (event.includes("STALE") && event.includes("EVIDENCE")) return "evidence.stale";
  if (event.includes("BLOCK")) return "case.blocked";
  if (event.includes("SAFETY") && event.includes("LOCK")) return "safety.locked";

  return null;
}

function zoneFor(raw: RawLedgerEvent): FactoryZoneKey | null {
  const room = String(raw.room || "").toUpperCase();
  return ROOM_MAP[room] ?? null;
}

export function adaptLedgerEvent(raw: RawLedgerEvent): AdaptedLedgerEvent {
  const eventType = String(raw.event_type || "").trim();
  const eventId = String(raw.event_id || "").trim();
  const caseId = String(raw.case_id || "").trim();
  const occurredAt = String(raw.created_at || "").trim();
  const type = canonicalType(eventType);
  const zone = zoneFor(raw);

  if (!eventType || !eventId || !caseId || !occurredAt) {
    return { raw, canonical: null, zone, reason: "Missing required audit-event identity fields." };
  }

  if (!type) {
    return { raw, canonical: null, zone, reason: `Unrecognized ledger event type: ${eventType}` };
  }

  return {
    raw,
    zone,
    reason: null,
    canonical: {
      eventId,
      caseId,
      eventType: type,
      occurredAt,
      room: zone,
      payload: raw.payload,
    },
  };
}

export function adaptLedgerEvents(events: readonly RawLedgerEvent[]) {
  return events.map(adaptLedgerEvent);
}
