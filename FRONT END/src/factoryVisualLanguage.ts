import type { FactoryCaseCondition, FactoryCaseStage } from "./factoryMovement";

export type FactoryVisualSignal = "NEON_ACTIVE" | "REVIEW" | "CAUTION" | "STOP" | "DARK" | "UNKNOWN";

export type FactoryVisualState = {
  signal: FactoryVisualSignal;
  pulse: boolean;
  maxLine: string;
  operatorLabel: string;
};

export const FACTORY_VISUALS_BY_CONDITION = {
  ACTIVE: {
    signal: "NEON_ACTIVE",
    pulse: true,
    operatorLabel: "ACTIVE",
    maxLine: "Keep it moving. Evidence first, ego last.",
  },
  WAITING: {
    signal: "REVIEW",
    pulse: false,
    operatorLabel: "WAITING",
    maxLine: "Nobody moves until the next receipt hits the desk.",
  },
  BLOCKED: {
    signal: "CAUTION",
    pulse: false,
    operatorLabel: "BLOCKED",
    maxLine: "Door's locked. Bring receipts.",
  },
  REJECTED: {
    signal: "STOP",
    pulse: false,
    operatorLabel: "REJECTED",
    maxLine: "Risk said no. Nobody gets whacked; the trade does.",
  },
  SAFETY_LOCK: {
    signal: "STOP",
    pulse: false,
    operatorLabel: "SAFETY LOCK",
    maxLine: "Live capital stays in the vault.",
  },
  STALE_EVIDENCE: {
    signal: "CAUTION",
    pulse: false,
    operatorLabel: "STALE EVIDENCE",
    maxLine: "Old intel belongs in the trunk, not the committee room.",
  },
  THESIS_BROKEN: {
    signal: "STOP",
    pulse: false,
    operatorLabel: "THESIS BROKEN",
    maxLine: "The thesis is dead. Stop arguing with the corpse.",
  },
  OFFLINE: {
    signal: "DARK",
    pulse: false,
    operatorLabel: "OFFLINE",
    maxLine: "Lights out. No telemetry, no theater.",
  },
  UNKNOWN: {
    signal: "UNKNOWN",
    pulse: false,
    operatorLabel: "UNKNOWN",
    maxLine: "I don't know means I don't know.",
  },
} satisfies Record<FactoryCaseCondition, FactoryVisualState>;

export const FACTORY_STAGE_LABELS = {
  EVIDENCE: "EVIDENCE WAREHOUSE",
  AGENTS: "SPECIALIST DESKS",
  COMMITTEE: "INVESTMENT COMMITTEE",
  SKEPTIC: "SKEPTIC / RED ROOM",
  RISK: "RISK INSPECTION",
  PAPER: "PAPER EXECUTION BAY",
  MONITORING: "PORTFOLIO / THESIS MONITORING",
  UNKNOWN: "LOCATION UNKNOWN",
} satisfies Record<FactoryCaseStage, string>;

export const X3_VISUAL_PRINCIPLES = [
  "Industrial noir before sci-fi: steel, glass, concrete, practical light, controlled neon.",
  "Mob/deal-room attitude lives in signage, copy, props, and character behavior—not in fake system activity.",
  "MAX reacts to real state changes only. He never creates a state or implies analysis that did not occur.",
  "Active rooms may glow or pulse only when backed by current telemetry or an accepted ledger transition.",
  "Safety, rejection, stale evidence, offline, and unknown states must be visually stronger than decorative success states.",
  "External research remains visually segregated from governed IIOS evidence even when it is useful.",
] as const;

export function visualStateFor(condition: FactoryCaseCondition): FactoryVisualState {
  return FACTORY_VISUALS_BY_CONDITION[condition];
}
