export type TruthRecord = Record<string, unknown>;

type TruthAvailability = "AVAILABLE" | "STALE" | "SOURCE_CONFLICT" | "UNAVAILABLE";
type TruthFreshness = "CURRENT" | "STALE" | "UNAVAILABLE";
const PROJECTED_LAYER_KEYS = ["factory_telemetry", "market_validation", "shadow_strategy", "outcome_learning"] as const;

export type GalleryTruth = {
  degraded: boolean;
  condition: "SANITIZED / OBSERVING" | "DEGRADED / INVESTIGATING";
  marketPhase: string;
  paperNav: number | null;
};

function record(value: unknown): TruthRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as TruthRecord
    : {};
}

async function getJson(path: string, signal?: AbortSignal): Promise<{ response: Response; data: TruthRecord }> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error(`${path} is unavailable`);
  }
  return { response, data: record(await response.json()) };
}

function isLocalhost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function isSafeRelativePath(value: string, origin: string): boolean {
  if (!value.startsWith("/") || value.startsWith("//")) return false;
  try { return new URL(value, origin).origin === origin; } catch { return false; }
}

function nullableString(value: unknown): boolean {
  return value === null || (typeof value === "string" && Boolean(value.trim()));
}

function nullableNumber(value: unknown): boolean {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function isTruthDto(value: TruthRecord): value is TruthRecord & { schema_version: string; generated_at: string | null; availability: TruthAvailability; source_conflict: boolean } {
  const availability = value.availability;
  const freshness = record(value.freshness);
  const factory = record(value.factory);
  const paperFund = record(factory.paper_fund);
  const validation = record(value.validation);
  const layers = record(validation.layers);
  const safety = record(value.safety);
  const generatedAtValid = typeof value.generated_at === "string" || value.generated_at === null;
  const ageValid = freshness.age_seconds === null
    || (typeof freshness.age_seconds === "number" && Number.isInteger(freshness.age_seconds) && freshness.age_seconds >= 0);
  const factoryValid = nullableString(factory.availability)
    && nullableNumber(factory.case_count)
    && nullableNumber(factory.event_count)
    && nullableNumber(factory.desk_count)
    && ["nav", "cash", "positions", "exposure"].every((key) => nullableNumber(paperFund[key]));
  const layerShapeValid = Object.values(layers).every((candidate) => {
    const layer = record(candidate);
    return nullableString(layer.availability) && nullableNumber(layer.age_seconds);
  });
  const layersValid = availability === "UNAVAILABLE"
    ? layerShapeValid
    : PROJECTED_LAYER_KEYS.every((key) => Object.hasOwn(layers, key)) && layerShapeValid;
  return value.schema_version === "living_wall_truth.v1"
    && generatedAtValid
    && ["AVAILABLE", "STALE", "SOURCE_CONFLICT", "UNAVAILABLE"].includes(String(availability))
    && typeof value.source_conflict === "boolean"
    && ["CURRENT", "STALE", "UNAVAILABLE"].includes(String(freshness.state))
    && ageValid
    && factoryValid
    && layersValid
    && safety.telemetry_read_only === true
    && safety.direct_ledger_access === false
    && safety.backend_write_permission === false
    && safety.trade_execution_permission === false
    && safety.live_execution === false;
}

export type TruthResult = {
  source: string;
  fallback: boolean;
  data: TruthRecord;
};

function text(value: unknown, fallback = "UNKNOWN"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function selectGalleryTruth(result: TruthResult | null, error: string | null = null): GalleryTruth {
  const data = record(result?.data);
  const remote = data.schema_version === "living_wall_truth.v1";
  if (remote) {
    const freshness = record(data.freshness);
    const factory = record(data.factory);
    const paperFund = record(factory.paper_fund);
    const layers = record(record(data.validation).layers);
    const marketValidation = record(layers.market_validation);
    const current = isTruthDto(data)
      && data.availability === "AVAILABLE"
      && freshness.state === "CURRENT"
      && data.source_conflict === false;
    const degraded = Boolean(error || result?.fallback || !current);
    return {
      degraded,
      condition: degraded ? "DEGRADED / INVESTIGATING" : "SANITIZED / OBSERVING",
      marketPhase: text(marketValidation.availability),
      paperNav: finiteNumber(paperFund.nav),
    };
  }

  const layers = record(record(data.validation).layers);
  const truthText = JSON.stringify(data).toUpperCase();
  const degraded = Boolean(
    !result
    || error
    || result?.fallback
    || /STALE|DEGRADED|OFFLINE|UNAVAILABLE|CONFLICT|INCOMPLETE_LINEAGE|MISSING_LINEAGE/.test(truthText)
    || Object.values(layers).some((layer) => /STALE|DEGRADED|OFFLINE|UNAVAILABLE|CONFLICT/.test(text(record(layer).availability, ""))),
  );
  return {
    degraded,
    condition: degraded ? "DEGRADED / INVESTIGATING" : "SANITIZED / OBSERVING",
    marketPhase: text(data.market_phase),
    paperNav: finiteNumber(data.paper_nav),
  };
}

export async function loadFactoryTruth(signal?: AbortSignal): Promise<TruthResult> {
  const hostname = window.location.hostname;
  const local = isLocalhost(hostname);
  const override = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_IIOS_TRUTH_ENDPOINT?.trim();
  const source = override && isSafeRelativePath(override, window.location.origin) && (local || override !== "/living/overview")
    ? override
    : local ? "/living/overview" : "/living-wall/truth";
  const { response, data } = await getJson(source, signal);
  if (local) {
    if (!response.ok) throw new Error(`${source} is unavailable`);
    return { source, fallback: false, data };
  }
  if (!isTruthDto(data)) throw new Error("remote truth response is invalid");
  if (!response.ok && data.availability !== "UNAVAILABLE") throw new Error(`${source} is unavailable`);
  const freshness = record(data.freshness);
  const availability = data.availability as TruthAvailability;
  const freshnessState = freshness.state as TruthFreshness;
  if (
    (availability === "AVAILABLE" && (freshnessState !== "CURRENT" || data.source_conflict !== false || data.generated_at === null))
    || (availability === "STALE" && freshnessState !== "STALE")
    || (availability === "SOURCE_CONFLICT" && data.source_conflict !== true)
    || (availability === "UNAVAILABLE" && (freshnessState !== "UNAVAILABLE" || data.generated_at !== null))
  ) throw new Error("remote truth state is inconsistent");
  const generatedAt = data.generated_at === null ? null : Date.parse(data.generated_at);
  if (generatedAt !== null && Number.isNaN(generatedAt)) throw new Error("remote truth timestamp is invalid");
  const previous = sessionStorage.getItem("iios.living-wall.truth.generated-at");
  if (generatedAt !== null && previous !== null && generatedAt < Number(previous)) {
    throw new Error("remote truth timestamp regressed");
  }
  if (generatedAt !== null) sessionStorage.setItem("iios.living-wall.truth.generated-at", String(generatedAt));
  return { source, fallback: false, data };
}
