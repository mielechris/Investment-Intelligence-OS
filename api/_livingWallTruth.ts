import { TELEMETRY_TTL_SECONDS } from "./_telemetryPolicy.js";

type JsonRecord = Record<string, unknown>;
type TruthAvailability = "AVAILABLE" | "STALE" | "SOURCE_CONFLICT" | "UNAVAILABLE";

export type LivingWallTruthDto = {
  schema_version: "living_wall_truth.v1";
  generated_at: string | null;
  freshness: { state: "CURRENT" | "STALE" | "UNAVAILABLE"; age_seconds: number | null };
  availability: TruthAvailability;
  source_conflict: boolean;
  factory: {
    availability: string | null;
    case_count: number | null;
    event_count: number | null;
    desk_count: number | null;
    paper_fund: { nav: number | null; cash: number | null; positions: number | null; exposure: number | null };
  };
  validation: { layers: Record<string, { availability: string | null; age_seconds: number | null }> };
  safety: {
    telemetry_read_only: true;
    direct_ledger_access: false;
    backend_write_permission: false;
    trade_execution_permission: false;
    live_execution: false;
  };
};

const MAX_FUTURE_SKEW_MS = 60_000;
const STALE_AFTER_SECONDS = 60;
const ALLOWED_LAYERS = ["factory_telemetry", "market_validation", "shadow_strategy", "outcome_learning"];

function record(value: unknown): JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function string(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null;
}

function layer(value: unknown): { availability: string | null; age_seconds: number | null } {
  const source = record(value);
  return { availability: string(source.availability), age_seconds: number(source.age_seconds) };
}

export function unavailableLivingWallTruth(): LivingWallTruthDto {
  return {
    schema_version: "living_wall_truth.v1",
    generated_at: null,
    freshness: { state: "UNAVAILABLE", age_seconds: null },
    availability: "UNAVAILABLE",
    source_conflict: false,
    factory: { availability: null, case_count: null, event_count: null, desk_count: null, paper_fund: { nav: null, cash: null, positions: null, exposure: null } },
    validation: { layers: {} },
    safety: { telemetry_read_only: true, direct_ledger_access: false, backend_write_permission: false, trade_execution_permission: false, live_execution: false },
  };
}

export function projectLivingWallTruth(input: unknown, now = Date.now()): LivingWallTruthDto {
  const snapshot = record(input);
  if (snapshot.schema_version !== undefined && snapshot.schema_version !== "iios_remote_telemetry.v1") {
    throw new Error("unsupported snapshot schema");
  }
  const generatedAt = string(snapshot.generated_at);
  const generatedMs = generatedAt === null ? Number.NaN : Date.parse(generatedAt);
  if (Number.isNaN(generatedMs)) throw new Error("unsupported snapshot timestamp");
  if (generatedMs > now + MAX_FUTURE_SKEW_MS) throw new Error("future snapshot timestamp");
  const ageSeconds = Math.max(0, Math.floor((now - generatedMs) / 1000));
  if (ageSeconds > TELEMETRY_TTL_SECONDS) throw new Error("expired snapshot");

  const safety = record(snapshot.safety);
  const layers = record(record(snapshot.validation).layers);
  const telemetryPayload = record(record(layers.factory_telemetry).payload);
  if (safety.live_execution !== false || record(telemetryPayload.safety).telemetry_read_only !== true) {
    throw new Error("unsafe snapshot");
  }

  const privateFactory = record(snapshot.factory);
  const factoryPayload = record(privateFactory.payload);
  const aggregate = Object.keys(factoryPayload).length ? factoryPayload : telemetryPayload;
  const paperFund = record(aggregate.paper_fund ?? aggregate.portfolio);
  const projectedLayers: LivingWallTruthDto["validation"]["layers"] = {};
  for (const key of ALLOWED_LAYERS) projectedLayers[key] = layer(layers[key]);
  const sourceConflict = snapshot.source_conflict === true || /CONFLICT/i.test(string(record(snapshot.source_status).state) ?? "");
  const freshnessState = ageSeconds > STALE_AFTER_SECONDS ? "STALE" : "CURRENT";

  return {
    schema_version: "living_wall_truth.v1",
    generated_at: generatedAt,
    freshness: { state: freshnessState, age_seconds: ageSeconds },
    availability: sourceConflict ? "SOURCE_CONFLICT" : freshnessState === "STALE" ? "STALE" : "AVAILABLE",
    source_conflict: sourceConflict,
    factory: {
      availability: string(privateFactory.availability ?? aggregate.availability ?? aggregate.health),
      case_count: count(aggregate.cases),
      event_count: count(aggregate.recent_events ?? aggregate.events ?? aggregate.recent_meaningful_events),
      desk_count: count(record(aggregate.factory).desks ?? aggregate.desks),
      paper_fund: { nav: number(paperFund.nav), cash: number(paperFund.cash), positions: number(paperFund.positions), exposure: number(paperFund.exposure) },
    },
    validation: { layers: projectedLayers },
    safety: { telemetry_read_only: true, direct_ledger_access: false, backend_write_permission: false, trade_execution_permission: false, live_execution: false },
  };
}