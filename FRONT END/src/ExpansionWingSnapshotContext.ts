import { createContext, useContext } from "react";

export type TruthState = "AVAILABLE" | "CURRENT" | "STALE" | "INCOMPLETE" | "UNAVAILABLE" | "UNKNOWN";
export type SnapshotSection = { state: TruthState; data: unknown };
export type ExpansionSnapshot = { schema_version: string; mode?: string; sections: Record<string, SnapshotSection>; authority: Record<string, boolean> };
export type SnapshotContextValue = { snapshot: ExpansionSnapshot | null; connection: TruthState; fixtureMode: boolean };

export const SnapshotContext = createContext<SnapshotContextValue>({ snapshot: null, connection: "UNKNOWN", fixtureMode: true });

export function useExpansionWingSnapshot(): SnapshotContextValue {
  return useContext(SnapshotContext);
}
