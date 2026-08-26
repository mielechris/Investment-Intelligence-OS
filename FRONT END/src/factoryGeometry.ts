import { FACTORY_ZONES } from "./experienceBlueprint";

export type FactoryZoneKey =
  | "intelligence-floor"
  | "agent-desks"
  | "research-annex"
  | "committee-room"
  | "skeptic-room"
  | "risk-inspection"
  | "paper-execution"
  | "portfolio-office"
  | "thesis-integrity"
  | "judgment-bank"
  | "evidence-warehouse"
  | "control-room";

export type FactoryFloorRect = {
  x: number;
  y: number;
  width: number;
  height: number;
  renderMode: "ROOM" | "OVERLAY";
};

export type FactoryRouteKind = "PRIMARY" | "CHALLENGE" | "KNOWLEDGE" | "OPERATIONS";

export type FactoryRoute = {
  key: string;
  from: FactoryZoneKey;
  to: FactoryZoneKey;
  kind: FactoryRouteKind;
  bidirectional?: boolean;
  description: string;
};

// Normalized 0-100 geometry. Renderers can scale this contract to any viewport.
// The Intelligence Floor is an overlay containing the physical rooms rather than
// a room that cases can occupy by itself.
export const FACTORY_FLOOR_GEOMETRY = {
  "intelligence-floor": { x: 0, y: 0, width: 100, height: 100, renderMode: "OVERLAY" },
  "evidence-warehouse": { x: 3, y: 5, width: 20, height: 22, renderMode: "ROOM" },
  "research-annex": { x: 3, y: 32, width: 20, height: 18, renderMode: "ROOM" },
  "control-room": { x: 3, y: 57, width: 20, height: 18, renderMode: "ROOM" },
  "agent-desks": { x: 28, y: 5, width: 26, height: 45, renderMode: "ROOM" },
  "judgment-bank": { x: 28, y: 57, width: 26, height: 18, renderMode: "ROOM" },
  "committee-room": { x: 59, y: 5, width: 17, height: 17, renderMode: "ROOM" },
  "skeptic-room": { x: 80, y: 5, width: 17, height: 17, renderMode: "ROOM" },
  "risk-inspection": { x: 59, y: 28, width: 17, height: 17, renderMode: "ROOM" },
  "paper-execution": { x: 80, y: 28, width: 17, height: 17, renderMode: "ROOM" },
  "portfolio-office": { x: 59, y: 52, width: 17, height: 18, renderMode: "ROOM" },
  "thesis-integrity": { x: 80, y: 52, width: 17, height: 18, renderMode: "ROOM" },
} satisfies Record<FactoryZoneKey, FactoryFloorRect>;

export const FACTORY_ROUTES = [
  {
    key: "evidence-to-desks",
    from: "evidence-warehouse",
    to: "agent-desks",
    kind: "PRIMARY",
    description: "Governed evidence enters specialist analysis.",
  },
  {
    key: "desks-to-committee",
    from: "agent-desks",
    to: "committee-room",
    kind: "PRIMARY",
    description: "Completed specialist work becomes committee input.",
  },
  {
    key: "committee-to-risk",
    from: "committee-room",
    to: "risk-inspection",
    kind: "PRIMARY",
    description: "Committee disposition advances to deterministic risk inspection.",
  },
  {
    key: "risk-to-paper",
    from: "risk-inspection",
    to: "paper-execution",
    kind: "PRIMARY",
    description: "Only risk-cleared cases may reach paper execution.",
  },
  {
    key: "paper-to-portfolio",
    from: "paper-execution",
    to: "portfolio-office",
    kind: "PRIMARY",
    description: "Paper fills become monitored portfolio state.",
  },
  {
    key: "portfolio-to-thesis",
    from: "portfolio-office",
    to: "thesis-integrity",
    kind: "PRIMARY",
    description: "Open paper positions are monitored separately for thesis integrity.",
  },
  {
    key: "committee-to-skeptic",
    from: "committee-room",
    to: "skeptic-room",
    kind: "CHALLENGE",
    bidirectional: true,
    description: "Material challenge can send a case through the Red Room and back to committee.",
  },
  {
    key: "research-to-desks",
    from: "research-annex",
    to: "agent-desks",
    kind: "KNOWLEDGE",
    description: "External research can enrich analysis but never bypass evidence lineage.",
  },
  {
    key: "judgment-to-desks",
    from: "judgment-bank",
    to: "agent-desks",
    kind: "KNOWLEDGE",
    description: "Governed human judgment can inform analysis with explicit lineage.",
  },
  {
    key: "thesis-to-committee",
    from: "thesis-integrity",
    to: "committee-room",
    kind: "CHALLENGE",
    description: "Material thesis change requires re-underwriting rather than silent continuation.",
  },
] as const satisfies readonly FactoryRoute[];

export function getFactoryZoneCenter(zoneKey: FactoryZoneKey) {
  const rect = FACTORY_FLOOR_GEOMETRY[zoneKey];
  return {
    x: rect.x + rect.width / 2,
    y: rect.y + rect.height / 2,
  };
}

export function validateFactoryGeometry(): string[] {
  const errors: string[] = [];
  const registryKeys = new Set(FACTORY_ZONES.map((zone) => zone.key));
  const geometryKeys = new Set(Object.keys(FACTORY_FLOOR_GEOMETRY));

  for (const key of registryKeys) {
    if (!geometryKeys.has(key)) errors.push(`Missing geometry for registry zone: ${key}`);
  }
  for (const key of geometryKeys) {
    if (!registryKeys.has(key)) errors.push(`Geometry contains unknown registry zone: ${key}`);
  }
  for (const route of FACTORY_ROUTES) {
    if (!geometryKeys.has(route.from)) errors.push(`Route ${route.key} has unknown origin: ${route.from}`);
    if (!geometryKeys.has(route.to)) errors.push(`Route ${route.key} has unknown destination: ${route.to}`);
  }

  return errors;
}
