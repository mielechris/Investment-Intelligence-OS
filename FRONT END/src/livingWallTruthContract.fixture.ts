// Sanitized HTTP 200 shape emitted by the living_wall_truth.v1 projector.
export const deployedAvailableTruth = {
  schema_version: "living_wall_truth.v1",
  generated_at: "2026-09-01T12:00:00Z",
  freshness: { state: "CURRENT", age_seconds: 1 },
  availability: "AVAILABLE",
  source_conflict: false,
  factory: {
    availability: "AVAILABLE",
    case_count: 40,
    event_count: null,
    desk_count: 8,
    paper_fund: { nav: 10000, cash: 10000, positions: 0, exposure: 0 },
  },
  validation: {
    layers: {
      factory_telemetry: { availability: "AVAILABLE", age_seconds: 1 },
      market_validation: { availability: "AVAILABLE", age_seconds: 87273 },
      shadow_strategy: { availability: "STALE", age_seconds: 85473 },
      outcome_learning: { availability: "AVAILABLE", age_seconds: 85 },
    },
  },
  safety: {
    telemetry_read_only: true,
    direct_ledger_access: false,
    backend_write_permission: false,
    trade_execution_permission: false,
    live_execution: false,
  },
};
