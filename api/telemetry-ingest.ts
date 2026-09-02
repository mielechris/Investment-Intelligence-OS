import { getCache } from "@vercel/functions";
import { createTelemetryIngestHandler } from "./_telemetryIngestHandler.js";

const cache = getCache({ namespace: "iios-remote-telemetry" });
export default {
  fetch: createTelemetryIngestHandler(
    cache,
    () => process.env.IIOS_TELEMETRY_INGEST_TOKEN ?? "",
  ),
};
