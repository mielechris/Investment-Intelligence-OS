import { getCache } from "@vercel/functions";
import { TELEMETRY_CACHE_KEY } from "./_telemetryPolicy.js";

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "GET") {
      return Response.json({ error: "method_not_allowed" }, { status: 405 });
    }

    const cache = getCache({ namespace: "iios-remote-telemetry" });
    const snapshot = await cache.get(TELEMETRY_CACHE_KEY);
    if (!snapshot) {
      return Response.json(
        {
          error: "telemetry_unavailable",
          message: "No current governed snapshot is available.",
          live_execution: false,
          telemetry_read_only: true,
        },
        {
          status: 503,
          headers: { "Cache-Control": "no-store" },
        },
      );
    }

    return Response.json(snapshot, {
      status: 200,
      headers: {
        "Cache-Control": "private, no-store",
        "X-IIOS-Telemetry-Mode": "read-only",
      },
    });
  },
};
