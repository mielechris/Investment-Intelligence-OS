import max from "./assets/v751/max.webp";
import policy from "./assets/v751/policy.webp";
import macro from "./assets/v751/macro.webp";
import fundamentals from "./assets/v751/fundamentals.webp";
import marketStructure from "./assets/v751/market_structure.webp";
import commodities from "./assets/v751/commodities.webp";
import geoWeather from "./assets/v751/geo_weather.webp";
import skeptic from "./assets/v751/skeptic.webp";
import portfolio from "./assets/v751/portfolio.webp";
import type { LivingCastKey } from "./livingCast";

/**
 * V7.5.1 final illustrated portrait registry.
 * Presentation-only artwork derived from the approved V7.5 Family Wall.
 * Persisted IIOS state remains authoritative.
 */
export const FINAL_PORTRAITS_V751: Record<LivingCastKey, string> = {
  max,
  policy,
  macro,
  fundamentals,
  market_structure: marketStructure,
  commodities,
  geo_weather: geoWeather,
  skeptic,
  portfolio,
};
