import { createContext, useContext } from "react";

export type TruthState = "AVAILABLE" | "CURRENT" | "STALE" | "INCOMPLETE" | "UNAVAILABLE" | "UNKNOWN";
export type PresentationStatus = TruthState | "NOT_ACTIVATED" | "AVAILABLE_EMPTY" | "AVAILABLE_FOR_REVIEWED_UPLOAD" | "SOURCE_REVIEW_REQUIRED";
export type SnapshotSection = { state: TruthState; data: unknown };
export type RoomState = { state: TruthState; presentation_status: PresentationStatus; data: unknown };
export type ExpansionSnapshot = { schema_version: string; mode?: string; sections: Record<string, SnapshotSection>; room_states?: Record<string, RoomState>; authority: Record<string, boolean> };
export type SnapshotContextValue = { snapshot: ExpansionSnapshot | null; connection: TruthState; fixtureMode: boolean; snapshotAgeSeconds: number | null };

export const SnapshotContext = createContext<SnapshotContextValue>({ snapshot: null, connection: "UNKNOWN", fixtureMode: true, snapshotAgeSeconds: null });

export function useExpansionWingSnapshot(): SnapshotContextValue {
  return useContext(SnapshotContext);
}
