const MAX_SNAPSHOT_BYTES = 512 * 1024;

const FORBIDDEN_KEYS = new Set([
  "api_key",
  "apikey",
  "password",
  "secret",
  "credential",
  "authorization",
  "access_token",
  "refresh_token",
  "private_key",
  "account_number",
  "broker_account",
]);

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function normalizedKey(key: string): string {
  return key.trim().toLowerCase().replaceAll("-", "_");
}

function assertSafeTree(value: unknown, path = "$"): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertSafeTree(item, `${path}[${index}]`));
    return;
  }
  if (value === null || typeof value !== "object") return;

  for (const [key, child] of Object.entries(value as JsonRecord)) {
    const normalized = normalizedKey(key);
    if (FORBIDDEN_KEYS.has(normalized)) {
      throw new Error(`forbidden telemetry field at ${path}.${key}`);
    }
    if (normalized === "live_execution" && child !== false) {
      throw new Error("live_execution must be false");
    }
    if (normalized === "telemetry_read_only" && child !== true) {
      throw new Error("telemetry_read_only must be true");
    }
    if (
      normalized === "write_authority" &&
      ![null, false, "none", "disabled", "read_only"].includes(
        typeof child === "string" ? child.toLowerCase() : child as null | false,
      )
    ) {
      throw new Error("write_authority must remain disabled");
    }
    if (
      normalized === "trade_authority" &&
      ![null, false, "none", "disabled"].includes(
        typeof child === "string" ? child.toLowerCase() : child as null | false,
      )
    ) {
      throw new Error("trade_authority must remain disabled");
    }
    assertSafeTree(child, `${path}.${key}`);
  }
}

export function validateSnapshot(input: unknown): JsonRecord {
  const snapshot = record(input);
  if (snapshot.schema_version !== REMOTE_SCHEMA_VERSION) {
    throw new Error("unsupported snapshot schema");
  }
  const generatedAt = snapshot.generated_at;
  if (typeof generatedAt !== "string" || Number.isNaN(Date.parse(generatedAt))) {
    throw new Error("generated_at must be an ISO timestamp");
  }

  const topSafety = record(snapshot.safety);
  if (topSafety.live_execution !== false) {
    throw new Error("snapshot must prove live_execution=false");
  }

  const validation = record(snapshot.validation);
  const layers = record(validation.layers);
  const factoryLayer = record(layers.factory_telemetry);
  const factoryPayload = record(factoryLayer.payload);
  const factorySafety = record(factoryPayload.safety);
  if (factorySafety.telemetry_read_only !== true) {
    throw new Error("snapshot must prove telemetry_read_only=true");
  }

  assertSafeTree(snapshot);
  const serialized = JSON.stringify(snapshot);
  if (new TextEncoder().encode(serialized).byteLength > MAX_SNAPSHOT_BYTES) {
    throw new Error("snapshot exceeds 512 KiB");
  }
  return snapshot;
}

export async function tokenMatches(candidate: string, expected: string): Promise<boolean> {
  if (!candidate || !expected) return false;
  const encoder = new TextEncoder();
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(candidate)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const a = new Uint8Array(left);
  const b = new Uint8Array(right);
  let mismatch = a.length ^ b.length;
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    mismatch |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return mismatch === 0;
}

export const TELEMETRY_CACHE_KEY = "iios:remote:living-overview:v1";
export const TELEMETRY_TTL_SECONDS = 120;
export const REMOTE_SCHEMA_VERSION = "iios_remote_telemetry.v1";
