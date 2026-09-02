import { TELEMETRY_CACHE_KEY } from "./_telemetryPolicy.js";
import { projectLivingWallTruth, unavailableLivingWallTruth } from "./_livingWallTruth.js";

type Cache = { get(key: string): Promise<unknown> };
export type TruthReadFailure = "MISSING_SNAPSHOT" | "INVALID_SNAPSHOT" | "STORAGE_ERROR";

function unavailableResponse(): Response {
  return Response.json(unavailableLivingWallTruth(), {
    status: 503,
    headers: { "Cache-Control": "private, no-store", "X-IIOS-Telemetry-Mode": "read-only" },
  });
}

export function createLivingWallTruthHandler(
  cache: Cache,
  reportFailure: (failure: TruthReadFailure) => void = (failure) => {
    console.warn(`[living-wall-truth] ${failure}`);
  },
) {
  return async function fetch(request: Request): Promise<Response> {
    if (request.method !== "GET") return Response.json({ error: "method_not_allowed" }, { status: 405 });
    let snapshot: unknown;
    try {
      snapshot = await cache.get(TELEMETRY_CACHE_KEY);
    } catch {
      reportFailure("STORAGE_ERROR");
      return unavailableResponse();
    }
    if (!snapshot) {
      reportFailure("MISSING_SNAPSHOT");
      return unavailableResponse();
    }
    try {
      return Response.json(projectLivingWallTruth(snapshot), {
        headers: { "Cache-Control": "private, no-store", "X-IIOS-Telemetry-Mode": "read-only" },
      });
    } catch {
      reportFailure("INVALID_SNAPSHOT");
      return unavailableResponse();
    }
  };
}
