import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { type ExpansionSnapshot, type RuntimeCapabilities, SnapshotContext, type TruthState } from "./ExpansionWingSnapshotContext";

const LIVE_READ_ONLY = import.meta.env.VITE_EXPANSION_WING_LIVE_READONLY === "1" && import.meta.env.VITE_BACKEND_RECOVERY_GREEN === "1";
const FIXTURE_MODE = import.meta.env.VITE_EXPANSION_WING_FIXTURE === "1";
const UNIFIED_FACTORY = import.meta.env.VITE_UNIFIED_LIVING_FACTORY === "1";
const EXPANSION_PATH = "/expansion-wing/snapshot";
const ENDPOINT = LIVE_READ_ONLY
  ? (import.meta.env.VITE_EXPANSION_WING_READONLY_ENDPOINT || (UNIFIED_FACTORY ? EXPANSION_PATH : "/snapshot"))
  : "/fixtures/expansion-wing.json";
const POLL_MS = 15_000;
const MAX_BACKOFF_MS = 60_000;
const CAPABILITIES_ENDPOINT = "/living/overview";

type RuntimeCapabilityWire = {
  schema_version?: unknown;
  configuration_source?: unknown;
  configuration_authenticated?: unknown;
  expansion_wing_enabled?: unknown;
  expansion_snapshot_path?: unknown;
  read_only?: unknown;
  publisher_control?: unknown;
};

function validateRuntimeCapabilities(value: unknown): RuntimeCapabilities {
  const envelope = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const capability = envelope.runtime_capabilities && typeof envelope.runtime_capabilities === "object" && !Array.isArray(envelope.runtime_capabilities)
    ? envelope.runtime_capabilities as RuntimeCapabilityWire
    : {};
  const valid = capability.schema_version === "iios-runtime-capabilities-v1"
    && capability.configuration_source === "SERVER_COMMAND_LINE"
    && capability.configuration_authenticated === true
    && typeof capability.expansion_wing_enabled === "boolean"
    && capability.read_only === true
    && capability.publisher_control === false
    && (capability.expansion_wing_enabled === false
      ? capability.expansion_snapshot_path === null
      : capability.expansion_snapshot_path === EXPANSION_PATH);
  if (!valid) return { state: "FAILED_CLOSED", expansionWingEnabled: false, readOnly: true, publisherControl: false };
  return { state: "CURRENT", expansionWingEnabled: capability.expansion_wing_enabled as boolean, readOnly: true, publisherControl: false };
}

async function requestJson(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { signal, cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("SANITIZED_READ_ONLY_SOURCE_UNAVAILABLE");
  return response.json() as Promise<unknown>;
}

function immutableSnapshot<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.freeze(value);
    Object.values(value).forEach((item) => immutableSnapshot(item));
  }
  return value;
}

const object = (value: unknown): Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const pickScalars = (value: unknown, keys: readonly string[]) => Object.fromEntries(keys.flatMap((key) => {
  const candidate = object(value)[key];
  return typeof candidate === "string" || typeof candidate === "number" || typeof candidate === "boolean" || candidate === null ? [[key, candidate]] : [];
}));
/** Reduces /living/overview to the exact scalar/event allowlist used by Museum presentation. */
function sanitizeMuseumOverview(value: unknown): Readonly<Record<string, unknown>> {
  const root = object(value), validation = object(root.validation), layers = object(validation.layers), telemetry = object(layers.factory_telemetry), payload = object(telemetry.payload), cadence = object(payload.cadence);
  const cadenceKeys = ["availability", "cadence_minutes", "cadence_state", "last_completed_at", "next_due_at", "worker"] as const;
  const events = Array.isArray(payload.recent_meaningful_events) ? payload.recent_meaningful_events.slice(0, 30).map((item) => pickScalars(item, ["created_at", "timestamp", "event_type", "case_id", "cycle_id"])) : [];
  return immutableSnapshot({
    generated_at: root.generated_at ?? null,
    cache: pickScalars(root.cache, ["freshness_state", "state"]),
    factory: pickScalars(root.factory, ["availability", "failure_category"]),
    validation: { layers: { factory_telemetry: { payload: {
      health: pickScalars(payload.health, ["state"]),
      cadence: { observation: pickScalars(cadence.observation, cadenceKeys), paper_trading: pickScalars(cadence.paper_trading, cadenceKeys), radar: pickScalars(cadence.radar, cadenceKeys) },
      paper_fund: pickScalars(payload.paper_fund, ["nav", "cash", "position_count", "transaction_count", "snapshot_as_of"]),
      radar: pickScalars(payload.radar, ["governed_universe_count", "last_cycle_completed_at", "last_cycle_id", "promoted_case_count", "promotion_candidate_count", "screener_hit_count"]),
      recent_meaningful_events: events,
    } } } },
  });
}

export function ExpansionWingSnapshotProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<ExpansionSnapshot | null>(null);
  const [sanitizedOverview, setSanitizedOverview] = useState<Readonly<Record<string, unknown>> | null>(null);
  const [connection, setConnection] = useState<TruthState>("UNKNOWN");
  const [runtimeCapabilities, setRuntimeCapabilities] = useState<RuntimeCapabilities>({ state: "UNKNOWN", expansionWingEnabled: false, readOnly: true, publisherControl: false });
  const receivedAt = useRef<number | null>(null);
  const controllerGeneration = useRef<{ readAt: number; sequence: number } | null>(null);
  const [snapshotAgeSeconds, setSnapshotAgeSeconds] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let timer: number | undefined;
    let failures = 0;
    const load = async () => {
      if (!active || controller) return;
      const requestController = new AbortController();
      controller = requestController;
      try {
        const overviewPayload = UNIFIED_FACTORY ? await requestJson(CAPABILITIES_ENDPOINT, requestController.signal) : null;
        const capability = UNIFIED_FACTORY
          ? validateRuntimeCapabilities(overviewPayload)
          : { state: "CURRENT" as TruthState, expansionWingEnabled: true, readOnly: true, publisherControl: false };
        if (capability.state === "FAILED_CLOSED") throw new Error("RUNTIME_CAPABILITY_FAILED_CLOSED");
        setRuntimeCapabilities(capability);
        if (active) setSanitizedOverview(overviewPayload && typeof overviewPayload === "object" && !Array.isArray(overviewPayload) ? sanitizeMuseumOverview(overviewPayload) : null);
        if (!capability.expansionWingEnabled) {
          if (active) { failures = 0; setSnapshot(null); setConnection("UNAVAILABLE"); }
          return;
        }
        const payload = immutableSnapshot(await requestJson(ENDPOINT, requestController.signal) as ExpansionSnapshot);
        if (active) {
          const controller = object(object(object(payload).sections).tuesday_controller_status);
          const controllerData = object(controller.data);
          const readAt = Date.parse(String(controllerData.controller_read_timestamp ?? ""));
          const sequence = Number(controllerData.controller_generation_sequence);
          const prior = controllerGeneration.current;
          if (Number.isFinite(readAt) && Number.isFinite(sequence)
              && prior !== null && (readAt < prior.readAt || (readAt === prior.readAt && sequence < prior.sequence))) return;
          if (Number.isFinite(readAt) && Number.isFinite(sequence)) controllerGeneration.current = { readAt, sequence };
          const now = Date.now();
          failures = 0; setSnapshot(payload); receivedAt.current = now; setSnapshotAgeSeconds(0); setConnection("CURRENT");
        }
      } catch (error) {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          failures += 1; setSnapshotAgeSeconds(receivedAt.current === null ? null : Math.max(0, Math.floor((Date.now() - receivedAt.current) / 1000)));
          setConnection(receivedAt.current === null ? "UNAVAILABLE" : "STALE");
          setRuntimeCapabilities((current) => current.expansionWingEnabled ? { ...current, state: "STALE" } : { state: "UNAVAILABLE", expansionWingEnabled: false, readOnly: true, publisherControl: false });
        }
      } finally {
        if (controller === requestController) controller = null;
        if (active) timer = window.setTimeout(() => void load(), Math.min(MAX_BACKOFF_MS, POLL_MS * 2 ** failures));
      }
    };
    void load();
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer); controller?.abort(); };
  }, []);
  const value = useMemo(() => ({ snapshot, sanitizedOverview, connection, fixtureMode: FIXTURE_MODE, snapshotAgeSeconds, runtimeCapabilities }), [snapshot, sanitizedOverview, connection, snapshotAgeSeconds, runtimeCapabilities]);
  return <SnapshotContext.Provider value={value}>{children}</SnapshotContext.Provider>;
}
