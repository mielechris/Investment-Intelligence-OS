import type { FactoryZoneKey } from "./factoryGeometry";

export type FactoryCaseStage =
  | "EVIDENCE"
  | "AGENTS"
  | "COMMITTEE"
  | "SKEPTIC"
  | "RISK"
  | "PAPER"
  | "MONITORING"
  | "UNKNOWN";

export type FactoryCaseCondition =
  | "ACTIVE"
  | "WAITING"
  | "BLOCKED"
  | "REJECTED"
  | "SAFETY_LOCK"
  | "STALE_EVIDENCE"
  | "THESIS_BROKEN"
  | "OFFLINE"
  | "UNKNOWN";

export type ThesisIntegrity = "INTACT" | "EARLY_BUT_INTACT" | "MATERIAL_CHANGE" | "THESIS_BROKEN" | "UNKNOWN";

export const FACTORY_EVENT_TYPES = [
  "case.created",
  "case.blocked",
  "case.unblocked",
  "evidence.loaded",
  "evidence.stale",
  "evidence.refreshed",
  "agent.assigned",
  "agent.thinking",
  "agent.completed",
  "committee.opened",
  "committee.completed",
  "challenge.raised",
  "challenge.cleared",
  "risk.inspected",
  "risk.cleared",
  "risk.rejected",
  "execution.approved",
  "execution.rejected",
  "paper.order.created",
  "paper.order.filled",
  "thesis.monitored",
  "thesis.status_changed",
  "safety.locked",
  "safety.unlocked",
] as const;

export type FactoryEventType = (typeof FACTORY_EVENT_TYPES)[number];

export type FactoryEventPayload = {
  reason?: string;
  thesisStatus?: ThesisIntegrity;
  [key: string]: unknown;
};

export type FactoryEvent = {
  eventId: string;
  caseId: string;
  eventType: FactoryEventType;
  occurredAt: string;
  room?: FactoryZoneKey | null;
  payload?: FactoryEventPayload;
};

export type FactoryCaseProjection = {
  caseId: string;
  stage: FactoryCaseStage;
  activeZone: FactoryZoneKey | null;
  condition: FactoryCaseCondition;
  thesisIntegrity: ThesisIntegrity;
  lastEvent: FactoryEvent | null;
  traversedStages: FactoryCaseStage[];
  anomalies: string[];
};

type EventRule = {
  allowedFrom: readonly FactoryCaseStage[] | "ANY";
  nextStage: FactoryCaseStage | "UNCHANGED";
  nextZone: FactoryZoneKey | null | "UNCHANGED";
};

const EVENT_RULES = {
  "case.created": { allowedFrom: ["UNKNOWN"], nextStage: "EVIDENCE", nextZone: "evidence-warehouse" },
  "case.blocked": { allowedFrom: "ANY", nextStage: "UNCHANGED", nextZone: "UNCHANGED" },
  "case.unblocked": { allowedFrom: "ANY", nextStage: "UNCHANGED", nextZone: "UNCHANGED" },
  "evidence.loaded": { allowedFrom: ["EVIDENCE"], nextStage: "EVIDENCE", nextZone: "evidence-warehouse" },
  "evidence.stale": { allowedFrom: "ANY", nextStage: "UNCHANGED", nextZone: "UNCHANGED" },
  "evidence.refreshed": { allowedFrom: "ANY", nextStage: "UNCHANGED", nextZone: "UNCHANGED" },
  "agent.assigned": { allowedFrom: ["EVIDENCE", "AGENTS"], nextStage: "AGENTS", nextZone: "agent-desks" },
  "agent.thinking": { allowedFrom: ["AGENTS"], nextStage: "AGENTS", nextZone: "agent-desks" },
  "agent.completed": { allowedFrom: ["AGENTS"], nextStage: "AGENTS", nextZone: "agent-desks" },
  "committee.opened": { allowedFrom: ["AGENTS", "COMMITTEE", "SKEPTIC", "MONITORING"], nextStage: "COMMITTEE", nextZone: "committee-room" },
  "committee.completed": { allowedFrom: ["COMMITTEE"], nextStage: "COMMITTEE", nextZone: "committee-room" },
  "challenge.raised": { allowedFrom: ["COMMITTEE"], nextStage: "SKEPTIC", nextZone: "skeptic-room" },
  "challenge.cleared": { allowedFrom: ["SKEPTIC"], nextStage: "COMMITTEE", nextZone: "committee-room" },
  "risk.inspected": { allowedFrom: ["COMMITTEE", "RISK"], nextStage: "RISK", nextZone: "risk-inspection" },
  "risk.cleared": { allowedFrom: ["RISK"], nextStage: "RISK", nextZone: "risk-inspection" },
  "risk.rejected": { allowedFrom: ["RISK"], nextStage: "RISK", nextZone: "risk-inspection" },
  "execution.approved": { allowedFrom: ["RISK", "PAPER"], nextStage: "PAPER", nextZone: "paper-execution" },
  "execution.rejected": { allowedFrom: ["RISK", "PAPER"], nextStage: "PAPER", nextZone: "paper-execution" },
  "paper.order.created": { allowedFrom: ["PAPER"], nextStage: "PAPER", nextZone: "paper-execution" },
  "paper.order.filled": { allowedFrom: ["PAPER"], nextStage: "PAPER", nextZone: "paper-execution" },
  "thesis.monitored": { allowedFrom: ["PAPER", "MONITORING"], nextStage: "MONITORING", nextZone: "portfolio-office" },
  "thesis.status_changed": { allowedFrom: ["MONITORING"], nextStage: "MONITORING", nextZone: "thesis-integrity" },
  "safety.locked": { allowedFrom: "ANY", nextStage: "UNCHANGED", nextZone: "UNCHANGED" },
  "safety.unlocked": { allowedFrom: "ANY", nextStage: "UNCHANGED", nextZone: "UNCHANGED" },
} satisfies Record<FactoryEventType, EventRule>;

const FACTORY_EVENT_TYPE_SET = new Set<string>(FACTORY_EVENT_TYPES);

export function isFactoryEventType(value: string): value is FactoryEventType {
  return FACTORY_EVENT_TYPE_SET.has(value);
}

export function createEmptyFactoryProjection(caseId: string): FactoryCaseProjection {
  return {
    caseId,
    stage: "UNKNOWN",
    activeZone: null,
    condition: "UNKNOWN",
    thesisIntegrity: "UNKNOWN",
    lastEvent: null,
    traversedStages: [],
    anomalies: [],
  };
}

function nextCondition(current: FactoryCaseCondition, event: FactoryEvent): FactoryCaseCondition {
  switch (event.eventType) {
    case "case.created":
    case "case.unblocked":
    case "evidence.loaded":
    case "evidence.refreshed":
    case "agent.assigned":
    case "agent.thinking":
    case "agent.completed":
    case "committee.opened":
    case "committee.completed":
    case "challenge.raised":
    case "challenge.cleared":
    case "risk.inspected":
    case "risk.cleared":
    case "execution.approved":
    case "paper.order.created":
    case "paper.order.filled":
    case "thesis.monitored":
    case "safety.unlocked":
      return "ACTIVE";
    case "case.blocked":
      return "BLOCKED";
    case "evidence.stale":
      return "STALE_EVIDENCE";
    case "risk.rejected":
    case "execution.rejected":
      return "REJECTED";
    case "safety.locked":
      return "SAFETY_LOCK";
    case "thesis.status_changed":
      return event.payload?.thesisStatus === "THESIS_BROKEN" ? "THESIS_BROKEN" : "ACTIVE";
    default:
      return current;
  }
}

function nextThesisIntegrity(current: ThesisIntegrity, event: FactoryEvent): ThesisIntegrity {
  if (event.eventType === "thesis.status_changed" && event.payload?.thesisStatus) return event.payload.thesisStatus;
  if (event.eventType === "thesis.monitored" && current === "UNKNOWN") return "EARLY_BUT_INTACT";
  return current;
}

export function applyFactoryEvent(current: FactoryCaseProjection, event: FactoryEvent): FactoryCaseProjection {
  if (event.caseId !== current.caseId) {
    return {
      ...current,
      anomalies: [...current.anomalies, `Ignored ${event.eventType}: case ${event.caseId} does not match ${current.caseId}.`],
    };
  }

  const rule = EVENT_RULES[event.eventType];
  const transitionAllowed = rule.allowedFrom === "ANY" || rule.allowedFrom.includes(current.stage);

  if (!transitionAllowed) {
    return {
      ...current,
      anomalies: [...current.anomalies, `Rejected transition ${current.stage} -> ${event.eventType}. No visual movement projected.`],
      lastEvent: event,
    };
  }

  const stage = rule.nextStage === "UNCHANGED" ? current.stage : rule.nextStage;
  const activeZone = rule.nextZone === "UNCHANGED" ? current.activeZone : rule.nextZone;
  const traversedStages = stage !== current.stage && stage !== "UNKNOWN"
    ? [...current.traversedStages, stage]
    : current.traversedStages;

  return {
    ...current,
    stage,
    activeZone: event.room ?? activeZone,
    condition: nextCondition(current.condition, event),
    thesisIntegrity: nextThesisIntegrity(current.thesisIntegrity, event),
    lastEvent: event,
    traversedStages,
  };
}

export function projectFactoryCase(caseId: string, events: readonly FactoryEvent[]): FactoryCaseProjection {
  return events.reduce<FactoryCaseProjection>(applyFactoryEvent, createEmptyFactoryProjection(caseId));
}

export function parseFactoryEvent(raw: unknown): FactoryEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const candidate = raw as Record<string, unknown>;
  const eventType = candidate.eventType ?? candidate.event_type;
  const eventId = candidate.eventId ?? candidate.event_id ?? candidate.id;
  const caseId = candidate.caseId ?? candidate.case_id;
  const occurredAt = candidate.occurredAt ?? candidate.occurred_at ?? candidate.created_at;

  if (typeof eventType !== "string" || !isFactoryEventType(eventType)) return null;
  if (typeof eventId !== "string" || typeof caseId !== "string" || typeof occurredAt !== "string") return null;

  const payload = candidate.payload && typeof candidate.payload === "object"
    ? candidate.payload as FactoryEventPayload
    : undefined;
  const room = typeof candidate.room === "string" ? candidate.room as FactoryZoneKey : undefined;

  return { eventId, caseId, eventType, occurredAt, room, payload };
}
