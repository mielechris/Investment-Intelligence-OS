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
  recognizedType: FactoryEventType | null;
  movementEligible: boolean;
  zone: FactoryZoneKey | null;
  reason: string | null;
};

const ROOM_MAP: Record<string, FactoryZoneKey> = {
  EVIDENCE: "evidence-warehouse",
  EIGHT_DESKS: "agent-desks",
  COMMITTEE: "committee-room",
  RISK: "risk-inspection",
  CAPITAL: "portfolio-office",
  PAPER_PORTFOLIO: "paper-execution",
};

function canonicalType(rawType: string): FactoryEventType | null {
  const event = rawType.toUpperCase();

  if (event.includes("SAFETY") && event.includes("UNLOCK")) return "safety.unlocked";
  if (event.includes("SAFETY") && event.includes("LOCK")) return "safety.locked";
  if (event.includes("STALE") && event.includes("EVIDENCE")) return "evidence.stale";
  if (event.includes("EVIDENCE") && (event.includes("REFRESH") || event.includes("UPDATED"))) return "evidence.refreshed";
  if (event.includes("CASE_CREATED")) return "case.created";
  if (event.includes("CASE_UNBLOCK") || event.includes("UNBLOCKED")) return "case.unblocked";
  if (event.includes("BLOCK")) return "case.blocked";
  if (event.includes("THESIS") && event.includes("BROKEN")) return "thesis.status_changed";
  if (event.includes("THESIS") || event.includes("MONITOR")) return "thesis.monitored";
  if (event.includes("PAPER_ORDER") && (event.includes("FILLED") || event.includes("EXECUTED"))) return "paper.order.filled";
  if (event.includes("PAPER_ORDER")) return "paper.order.created";
  if (event.includes("PAPER_EXECUTION") && (event.includes("REJECT") || event.includes("DENY"))) return "execution.rejected";
  if (event.includes("PAPER_EXECUTION")) return "execution.approved";
  if (event.includes("RISK_REJECT") || event.includes("RISK_DENY")) return "risk.rejected";
  if (event.includes("RISK_COMPLETE") || event.includes("RISK_CLEAR") || event.includes("RISK_AUTH")) return "risk.cleared";
  if (event.includes("RISK_")) return "risk.inspected";
  if (event.includes("CHALLENGE") && event.includes("CLEAR")) return "challenge.cleared";
  if (event.includes("CHALLENGE") || event.includes("SKEPTIC") || event.includes("RED_TEAM")) return "challenge.raised";
  if (event.includes("COMMITTEE_COMPLETE") || event.includes("COUNCIL_COMPLETE")) return "committee.completed";
  if (event.includes("COMMITTEE") || event.includes("COUNCIL")) return "committee.opened";
  if (event.includes("AGENT_COMPLETE") || event.includes("SPECIALIST_COMPLETE") || event.includes("DESK_COMPLETE")) return "agent.completed";
  if (event.includes("AGENT_THINK") || event.includes("SPECIALIST_THINK") || event.includes("DESK_THINK")) return "agent.thinking";
  if (event.includes("AGENT_START") || event.includes("SPECIALIST_START") || event.includes("DESK_START") || event.includes("AGENT_ASSIGNED")) return "agent.assigned";
  if (event.includes("EVIDENCE") || event.includes("INGEST") || event.includes("PRIMARY_")) return "evidence.loaded";

  return null;
}

function inferredZoneForType(type: FactoryEventType | null): FactoryZoneKey | null {
  if (!type) return null;
  if (type.startsWith("committee.")) return "committee-room";
  if (type.startsWith("challenge.")) return "skeptic-room";
  if (type.startsWith("risk.")) return "risk-inspection";
  if (type.startsWith("execution.") || type.startsWith("paper.")) return "paper-execution";
  if (type.startsWith("agent.")) return "agent-desks";
  if (type.startsWith("evidence.")) return "evidence-warehouse";
  if (type.startsWith("thesis.")) return "thesis-integrity";
  return null;
}

function zoneFor(raw: RawLedgerEvent, type: FactoryEventType | null): FactoryZoneKey | null {
  const room = String(raw.room || "").toUpperCase();
  return ROOM_MAP[room] ?? inferredZoneForType(type);
}

export function adaptLedgerEvent(raw: RawLedgerEvent): AdaptedLedgerEvent {
  const eventType = String(raw.event_type || "").trim();
  const eventId = String(raw.event_id || "").trim();
  const caseId = String(raw.case_id || "").trim();
  const occurredAt = String(raw.created_at || "").trim();
  const type = canonicalType(eventType);
  const zone = zoneFor(raw, type);

  if (!eventType || !type) {
    return {
      raw,
      canonical: null,
      recognizedType: null,
      movementEligible: false,
      zone,
      reason: eventType ? `Unrecognized ledger event type: ${eventType}` : "Missing event type.",
    };
  }

  if (!eventId || !caseId || !occurredAt) {
    return {
      raw,
      canonical: null,
      recognizedType: type,
      movementEligible: false,
      zone,
      reason: "Recognized system event, but case/audit identity is incomplete; no case movement projected.",
    };
  }

  return {
    raw,
    zone,
    recognizedType: type,
    movementEligible: true,
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
