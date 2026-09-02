import { getCache } from "@vercel/functions";
import { createLivingWallTruthHandler } from "./_livingWallTruthHandler.js";

const cache = getCache({ namespace: "iios-remote-telemetry" });
export default { fetch: createLivingWallTruthHandler(cache) };