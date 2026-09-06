import { FINAL_PORTRAITS_V751 } from "./finalPortraitsV751";
import { LIVING_CAST, type LivingCastKey } from "./livingCast";

export type MuseumPortraitPresentation = {
  asset: string; sourceWidth: 560; sourceHeight: 700; mode: "intrinsic";
  focalX: 50; focalY: 50; safeInset: 0; maximumRenderedWidth: 360; alt: string;
};

export const MUSEUM_PORTRAIT_PRESENTATION: Readonly<Record<LivingCastKey, MuseumPortraitPresentation>> = Object.freeze(
  Object.fromEntries((Object.keys(LIVING_CAST) as LivingCastKey[]).map((key) => [key, {
    asset: FINAL_PORTRAITS_V751[key], sourceWidth: 560 as const, sourceHeight: 700 as const,
    mode: "intrinsic" as const, focalX: 50 as const, focalY: 50 as const, safeInset: 0 as const,
    maximumRenderedWidth: 360 as const, alt: `${LIVING_CAST[key].displayName}, ${LIVING_CAST[key].governedRole}`,
  }])) as Record<LivingCastKey, MuseumPortraitPresentation>,
);
