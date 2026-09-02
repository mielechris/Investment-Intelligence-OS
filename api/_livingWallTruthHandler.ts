import { TELEMETRY_CACHE_KEY } from "./_telemetryPolicy.js";
import { projectLivingWallTruth, unavailableLivingWallTruth } from "./_livingWallTruth.js";

type Cache = { get(key: string): Promise<unknown> };

export function createLivingWallTruthHandler(cache: Cache) {
  return async function fetch(request: Request): Promise<Response> {
    if (request.method !== "GET") return Response.json({ error: "method_not_allowed" }, { status: 405 });
    try {
      const snapshot = await cache.get(TELEMETRY_CACHE_KEY);
      if (!snapshot) throw new Error("missing snapshot");
      return Response.json(projectLivingWallTruth(snapshot), {
        headers: { "Cache-Control": "private, no-store", "X-IIOS-Telemetry-Mode": "read-only" },
      });
    } catch {
      return Response.json(unavailableLivingWallTruth(), {
        status: 503,
        headers: { "Cache-Control": "private, no-store", "X-IIOS-Telemetry-Mode": "read-only" },
      });
    }
  };
}