import { FINAL_PORTRAITS_V751 } from "./finalPortraitsV751";
import maxMove from "./assets/v752/max-move.webp";
import policyMove from "./assets/v752/policy-move.webp";
import macroMove from "./assets/v752/macro-move.webp";
import fundamentalsMove from "./assets/v752/fundamentals-move.webp";
import marketStructureMove from "./assets/v752/market_structure-move.webp";
import commoditiesMove from "./assets/v752/commodities-move.webp";
import geoWeatherMove from "./assets/v752/geo_weather-move.webp";
import skepticMove from "./assets/v752/skeptic-move.webp";
import portfolioMove from "./assets/v752/portfolio-move.webp";
import type { LivingCastKey } from "./livingCast";

/**
 * V7.5.2 avatar presentation registries.
 * Large cinematic portraits retain the approved V7.5.1 cuts.
 * Moving avatars use tighter head/torso cuts from the same approved HQ wall.
 * Artwork remains presentation-only; persisted IIOS state is authoritative.
 */
export const CINEMATIC_PORTRAITS_V752: Record<LivingCastKey, string> =
  FINAL_PORTRAITS_V751;

export const MOVING_PORTRAITS_V752: Record<LivingCastKey, string> = {
  max: maxMove,
  policy: policyMove,
  macro: macroMove,
  fundamentals: fundamentalsMove,
  market_structure: marketStructureMove,
  commodities: commoditiesMove,
  geo_weather: geoWeatherMove,
  skeptic: skepticMove,
  portfolio: portfolioMove,
};
