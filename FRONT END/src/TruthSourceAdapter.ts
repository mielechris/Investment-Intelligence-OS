export type TruthRecord = Record<string, unknown>;

type TruthAvailability = "AVAILABLE" | "STALE" | "SOURCE_CONFLICT" | "UNAVAILABLE";

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

function isTruthDto(value: TruthRecord): value is TruthRecord & { schema_version: string; generated_at: string | null; availability: TruthAvailability; source_conflict: boolean } {
  const availability = value.availability;
  const freshness = record(value.freshness);
  const safety = record(value.safety);
  return value.schema_version === "living_wall_truth.v1"
    && (typeof value.generated_at === "string" || value.generated_at === null)
    && ["AVAILABLE", "STALE", "SOURCE_CONFLICT", "UNAVAILABLE"].includes(String(availability))
    && typeof value.source_conflict === "boolean"
    && ["CURRENT", "STALE", "UNAVAILABLE"].includes(String(freshness.state))
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
  const generatedAt = data.generated_at === null ? null : Date.parse(data.generated_at);
  if (generatedAt !== null && Number.isNaN(generatedAt)) throw new Error("remote truth timestamp is invalid");
  const previous = sessionStorage.getItem("iios.living-wall.truth.generated-at");
  if (generatedAt !== null && previous !== null && generatedAt < Number(previous)) {
    throw new Error("remote truth timestamp regressed");
  }
  if (generatedAt !== null) sessionStorage.setItem("iios.living-wall.truth.generated-at", String(generatedAt));
  return { source, fallback: false, data };
}