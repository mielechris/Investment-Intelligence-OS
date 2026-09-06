import type { ExpansionSnapshot, TruthState } from "./ExpansionWingSnapshotContext";

export type TruthRecord = Record<string, unknown>;
export type TruthResult = { source: string; fallback: boolean; data: TruthRecord };
export type GalleryTruth = { degraded: boolean; condition: string; marketPhase: string; paperNav: number | null };

const record = (value: unknown): TruthRecord => value && typeof value === "object" && !Array.isArray(value) ? value as TruthRecord : {};

/** Pure presentation adapter. Network ownership remains exclusively in ExpansionWingSnapshotProvider. */
export function adaptExpansionSnapshot(snapshot: ExpansionSnapshot, connection: TruthState, ageSeconds: number | null): TruthResult {
  const section = (name: string) => snapshot.sections[name];
  const books = record(section("books")?.data);
  const factory = record(section("multi_asset_factory")?.data);
  const conveyor = record(section("candidate_conveyor")?.data);
  const candidates = Array.isArray(conveyor.candidates) && connection === "CURRENT" && section("candidate_conveyor")?.state === "CURRENT" ? conveyor.candidates : [];
  const events = candidates.flatMap((candidate, index) => {
    const value = record(candidate);
    return typeof value.candidate_id === "string" && typeof value.discovery_timestamp === "string"
      ? [{ event_id: `candidate:${index}`, event_type: "radar_discovery", created_at: value.discovery_timestamp, entity_id: value.candidate_id, source_identity: "SANITIZED_CANDIDATE_LINEAGE" }]
      : [];
  });
  const prohibited = Object.entries(snapshot.authority).some(([key, value]) => key !== "paper_mode" && value === true);
  const freshness = connection === "CURRENT" && section("projection_freshness")?.state === "CURRENT" ? "CURRENT" : connection === "UNAVAILABLE" ? "UNAVAILABLE" : "STALE";
  const availability = prohibited ? "SOURCE_CONFLICT" : connection === "CURRENT" ? "AVAILABLE" : connection === "UNAVAILABLE" ? "UNAVAILABLE" : "STALE";
  return { source: "same-origin-expansion-snapshot", fallback: false, data: {
    schema_version: "living_wall_truth.v1", availability, generated_at: null,
    freshness: { state: freshness, age_seconds: ageSeconds },
    safety: { telemetry_read_only: true, direct_ledger_access: false, backend_write_permission: false, trade_execution_permission: false, live_execution: false },
    factory: { availability: section("service_health")?.state ?? "UNAVAILABLE", payload: { recent_events: events, cases: [] }, paper_fund: { nav: factory.consolidated_paper_nav ?? books.total ?? null, cash: books.cash ?? null } },
    validation: { layers: { market_validation: { availability: section("benchmark_9h")?.state ?? "UNAVAILABLE" } } },
  } };
}
