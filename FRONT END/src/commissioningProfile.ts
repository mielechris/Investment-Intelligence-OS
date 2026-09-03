export type BrightnessProfile = "exhibition" | "conservation" | "evening";
export type ProtectionState = "awake" | "dim" | "rest";

export const BRIGHTNESS_PROFILES: Record<BrightnessProfile, { label: string; sceneLevel: number }> = {
  exhibition: { label: "Exhibition", sceneLevel: 1 },
  conservation: { label: "Conservation", sceneLevel: 0.82 },
  evening: { label: "Evening", sceneLevel: 0.68 },
};

export const COMMISSIONING_PROFILE = {
  schemaVersion: "iios_auction_wall_display.v1",
  edition: "Museum Master 1.2 / 77-Inch Commissioning Edition",
  nativeResolution: [3840, 2160] as const,
  safeZonePercent: 2,
  viewingDistanceFeet: [8, 12] as const,
  dimStartHour: 22,
  restStartHour: 1,
  wakeHour: 7,
  unavailableDimMinutes: 5,
  unavailableRestMinutes: 30,
  pixelDriftPixels: 1,
} as const;

export function scheduledProtectionState(hour: number): ProtectionState {
  if (hour >= COMMISSIONING_PROFILE.dimStartHour || hour < COMMISSIONING_PROFILE.wakeHour) {
    return hour >= COMMISSIONING_PROFILE.restStartHour && hour < COMMISSIONING_PROFILE.wakeHour ? "rest" : "dim";
  }
  return "awake";
}

export function resolveProtectionState(now: Date, unavailableSince: number | null): ProtectionState {
  const scheduled = scheduledProtectionState(now.getHours());
  if (unavailableSince === null) return scheduled;
  const unavailableMinutes = Math.max(0, (now.getTime() - unavailableSince) / 60_000);
  if (unavailableMinutes >= COMMISSIONING_PROFILE.unavailableRestMinutes) return "rest";
  if (unavailableMinutes >= COMMISSIONING_PROFILE.unavailableDimMinutes && scheduled === "awake") return "dim";
  return scheduled;
}

export function nextBrightnessProfile(current: BrightnessProfile): BrightnessProfile {
  const profiles: BrightnessProfile[] = ["exhibition", "conservation", "evening"];
  return profiles[(profiles.indexOf(current) + 1) % profiles.length] ?? "exhibition";
}
