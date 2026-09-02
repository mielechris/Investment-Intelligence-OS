export type TruthRecord = Record<string, unknown>;

function record(value: unknown): TruthRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as TruthRecord
    : {};
}

async function getJson(path: string, signal?: AbortSignal): Promise<TruthRecord> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) {
    throw new Error(`${path} is unavailable`);
  }
  return record(await response.json());
}

export type TruthResult = {
  source: string;
  fallback: boolean;
  data: TruthRecord;
};

export async function loadFactoryTruth(signal?: AbortSignal): Promise<TruthResult> {
  const canonical = import.meta.env.VITE_IIOS_TRUTH_ENDPOINT?.trim();
  if (!canonical) {
    return { source: "/living/overview", fallback: true, data: await getJson("/living/overview", signal) };
  }
  try {
    return { source: canonical, fallback: false, data: await getJson(canonical, signal) };
  } catch {
    return { source: "/living/overview", fallback: true, data: await getJson("/living/overview", signal) };
  }
}