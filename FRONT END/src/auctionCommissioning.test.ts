import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { AUCTION_ROOMS } from "./auctionRegistry.ts";
import { buildAuctionModel } from "./auctionSceneModel.ts";
import { COMMISSIONING_PROFILE, nextBrightnessProfile, resolveProtectionState, scheduledProtectionState } from "./commissioningProfile.ts";
import { resolveAuctionPresentation } from "./auctionPresentation.ts";

const app = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const factory = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./AuctionEdition.css", import.meta.url), "utf8");
const configText = readFileSync(new URL("../../config/auction_wall_display.example.json", import.meta.url), "utf8");
const config = JSON.parse(configText);

test("77-inch profile fixes the native 4K canvas and two-percent safe zone", () => {
  assert.deepEqual(COMMISSIONING_PROFILE.nativeResolution, [3840, 2160]);
  assert.equal(3840 / 2160, 16 / 9);
  assert.equal(COMMISSIONING_PROFILE.safeZonePercent, 2);
  assert.deepEqual(COMMISSIONING_PROFILE.viewingDistanceFeet, [8, 12]);
  assert.equal(config.display.diagonal_inches, 77);
  assert.equal(config.display.target_resolution, "3840x2160");
  assert.equal(config.display.safe_zone_percent, 2);
  assert.match(css, /@media\(min-width:3000px\) and \(min-aspect-ratio:16\/10\)/);
  assert.match(css, /--commissioning-safe-zone:2vw/);
});

test("all eighteen rooms remain mounted, identified, and interactive", () => {
  assert.equal(AUCTION_ROOMS.length, 18);
  assert.equal(new Set(AUCTION_ROOMS.map((room) => room.id)).size, 18);
  assert.match(factory, /data-testid="auction-room"/);
  assert.match(factory, /data-room-id=\{room\.id\}/);
  assert.match(factory, /onClick=\{open\}/);
  assert.doesNotMatch(css, /auction-master-1-2[^}]*auction-room[^}]*display:none/);
});

test("MAX dominance and wall-readable collector markings are explicit", () => {
  assert.match(factory, /data-testid="auction-max"/);
  assert.match(css, /auction-master-1-2 \.auction-max-walkway\{width:22%;min-width:590px\}/);
  assert.match(app, /Museum Master 1\.2 \/ 77-Inch Commissioning Edition/);
  assert.match(app, /<span>GOVERNED READ MODEL<\/span>/);
  assert.match(css, /auction-gallery-caption small span\{white-space:nowrap\}/);
});

test("Gallery, Wall Art, pause, reduced motion, and Safety Lock preserve architecture", () => {
  for (const options of [
    { wallMode: false, paused: false, reducedMotion: false, safetyLocked: false },
    { wallMode: true, paused: false, reducedMotion: false, safetyLocked: false },
    { wallMode: true, paused: true, reducedMotion: false, safetyLocked: false },
    { wallMode: true, paused: false, reducedMotion: true, safetyLocked: false },
    { wallMode: true, paused: false, reducedMotion: false, safetyLocked: true },
  ]) {
    const result = resolveAuctionPresentation({ mode: "gallery", ...options });
    assert.equal(result.factoryVisible, true);
  }
  assert.match(app, /window\.matchMedia\("\(prefers-reduced-motion: reduce\)"\)/);
  assert.match(app, /SAFETY LOCK/);
});

test("unavailable truth remains fail-closed with every room and safety indicator visible", () => {
  const model = buildAuctionModel(null, "offline", new Date("2026-09-03T12:00:00Z"));
  assert.equal(model.condition, "UNAVAILABLE");
  assert.equal(Object.keys(model.rooms).length, 18);
  assert.deepEqual(model.motion, { ambient: false, evidence: false, reason: "FROZEN_UNSAFE" });
  assert.match(app, /auction-wall-health/);
  assert.match(app, /READ ONLY · LEDGER FALSE · WRITE FALSE · TRADE FALSE · LIVE FALSE/);
  assert.match(css, /protection-rest \.auction-wall-health/);
});

test("brightness, scheduled dim and unavailable rest are deterministic", () => {
  assert.equal(nextBrightnessProfile("exhibition"), "conservation");
  assert.equal(nextBrightnessProfile("conservation"), "evening");
  assert.equal(nextBrightnessProfile("evening"), "exhibition");
  assert.equal(scheduledProtectionState(12), "awake");
  assert.equal(scheduledProtectionState(23), "dim");
  assert.equal(scheduledProtectionState(2), "rest");
  const now = new Date("2026-09-03T12:31:00Z");
  now.setHours(12);
  assert.equal(resolveProtectionState(now, now.getTime() - 6 * 60_000), "dim");
  assert.equal(resolveProtectionState(now, now.getTime() - 31 * 60_000), "rest");
});

test("pixel drift changes paint only and stops for pause, rest, and reduced motion", () => {
  assert.equal(COMMISSIONING_PROFILE.pixelDriftPixels, 1);
  assert.match(css, /@keyframes auction-pixel-drift/);
  assert.match(css, /translate3d\(1px,1px,0\)/);
  assert.match(css, /is-paused \.auction-scene-plane[^}]*animation:none!important/);
  assert.match(css, /is-reduced-motion \.auction-scene-plane[^}]*animation:none!important/);
  assert.match(css, /protection-rest \.auction-scene-plane[^}]*animation:none!important/);
  assert.doesNotMatch(css, /@keyframes auction-pixel-drift[^}]*\b(?:width|height|inset|display|visibility)\b/);
});

test("dialogs, Case Theater, Collector Plaque, and fullscreen controls remain accessible", () => {
  assert.match(app, /CASE THEATER \/ READ ONLY/);
  assert.match(app, /CollectorPlaque/);
  assert.match(app, /role="dialog" aria-modal="true"/);
  assert.match(app, /Enter Full Screen/);
  assert.match(app, /Exit Full Screen/);
  assert.match(app, /Reveal Controls/);
  assert.match(app, /Ownership grants no trading authority, credentials, source-control access/);
});

test("configuration keeps OLED protection and recovery fail-closed", () => {
  assert.equal(config.display.panel_oled_protection_enabled, true);
  assert.equal(config.recovery.network_failure_mode, "fail_closed_visible_architecture");
  assert.equal(config.browser.fullscreen_manual_confirmation, true);
  assert.equal(config.browser.kiosk_exit_accessible, true);
  assert.equal(config.browser.startup_automation_enabled, false);
});
