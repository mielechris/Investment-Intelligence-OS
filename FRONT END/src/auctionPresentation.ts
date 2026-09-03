export type AuctionMode = "gallery" | "story" | "replay" | "command" | "expansion" | "watch";

export type AuctionPresentation = {
  effectiveMode: AuctionMode;
  factoryVisible: boolean;
  motionFrozen: boolean;
  compactSafetyIndicator: boolean;
};

export function resolveAuctionPresentation({ mode, wallMode, paused, reducedMotion, safetyLocked }: { mode: AuctionMode; wallMode: boolean; paused: boolean; reducedMotion: boolean; safetyLocked: boolean }): AuctionPresentation {
  const effectiveMode = wallMode ? "gallery" : mode;
  return {
    effectiveMode,
    factoryVisible: effectiveMode === "gallery",
    motionFrozen: paused || reducedMotion || safetyLocked,
    compactSafetyIndicator: wallMode && safetyLocked,
  };
}
