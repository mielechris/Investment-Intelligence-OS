import { getCache } from "@vercel/functions";
import {
  TELEMETRY_CACHE_KEY,
  TELEMETRY_TTL_SECONDS,
  tokenMatches,
  validateSnapshot,
} from "./_telemetryPolicy.js";

function json(body: unknown, status: number): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") {
      return json({ error: "method_not_allowed" }, 405);
    }

    const expected = process.env.IIOS_TELEMETRY_INGEST_TOKEN ?? "";
    const authorization = request.headers.get("x-iios-telemetry-token") ?? "";
    const candidate = authorization.startsWith("Bearer ")
      ? authorization.slice("Bearer ".length)
      : "";
    if (!(await tokenMatches(candidate, expected))) {
      return json({ error: "unauthorized" }, 401);
    }

    const contentLength = Number(request.headers.get("content-length") ?? "0");
    if (contentLength > 512 * 1024) {
      return json({ error: "payload_too_large" }, 413);
    }

    try {
      const snapshot = validateSnapshot(await request.json());
      const cache = getCache({ namespace: "iios-remote-telemetry" });
      await cache.set(TELEMETRY_CACHE_KEY, snapshot, {
        ttl: TELEMETRY_TTL_SECONDS,
        tags: ["iios-living-overview"],
      });
      return json(
        {
          accepted: true,
          generated_at: snapshot.generated_at,
          expires_in_seconds: TELEMETRY_TTL_SECONDS,
          live_execution: false,
          telemetry_read_only: true,
        },
        202,
      );
    } catch (error) {
      return json(
        {
          error: "snapshot_rejected",
          reason: error instanceof Error ? error.message : "invalid snapshot",
        },
        400,
      );
    }
  },
};
