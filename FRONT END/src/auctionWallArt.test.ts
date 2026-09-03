import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { AUCTION_ROOMS } from "./auctionRegistry.ts";
import { resolveAuctionPresentation } from "./auctionPresentation.ts";
import { buildAuctionModel } from "./auctionSceneModel.ts";

const app = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const factory = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./AuctionEdition.css", import.meta.url), "utf8");

function assertFactoryVisible(options: { paused?: boolean; reducedMotion?: boolean; safetyLocked?: boolean } = {}) {
  const frame = resolveAuctionPresentation({ mode: "command", wallMode: true, paused: options.paused ?? false, reducedMotion: options.reducedMotion ?? false, safetyLocked: options.safetyLocked ?? false });
  assert.equal(frame.effectiveMode, "gallery");
  assert.equal(frame.factoryVisible, true);
  return frame;
}

test("Wall Art Mode always resolves to Gallery with the complete factory mounted", () => {
  assertFactoryVisible();
  assert.equal(AUCTION_ROOMS.length, 18);
  assert.match(app, /presentation\.factoryVisible \? <Gallery/);
  assert.match(factory, /AUCTION_ROOMS\.slice\(0, 5\).*AUCTION_ROOMS\.slice\(5, 10\).*AUCTION_ROOMS\.slice\(10\)/s);
  assert.match(factory, /auction-max-walkway/);
  assert.doesNotMatch(css, /\.auction-shell\.is-wall-mode[^\n{]*\.auction-(factory|building|level|max-walkway|room)[^{]*\{[^}]*display:none/);
});

test("Wall Art Mode plus Safety Lock preserves architecture and freezes motion", () => {
  const frame = assertFactoryVisible({ safetyLocked: true });
  assert.equal(frame.motionFrozen, true);
  assert.equal(frame.compactSafetyIndicator, true);
  assert.match(app, /SafetyCurtain compact=\{presentation\.compactSafetyIndicator\}/);
  assert.match(css, /\.auction-shell\.is-wall-mode \.auction-safety-curtain\.is-compact/);
  assert.match(css, /\.is-motion-frozen \.auction-building[^}]*clip-path:inset\(0\);filter:none/);
});

test("Wall Art Mode plus paused scene preserves architecture and freezes animation only", () => {
  const frame = assertFactoryVisible({ paused: true });
  assert.equal(frame.motionFrozen, true);
  assert.match(css, /\.is-paused \.auction-building/);
  assert.doesNotMatch(css, /\.is-paused[^\n{]*(auction-factory|auction-building|auction-level|auction-room)[^{]*\{[^}]*display:none/);
});

test("Wall Art Mode plus reduced motion preserves architecture and disables animation", () => {
  const frame = assertFactoryVisible({ reducedMotion: true });
  assert.equal(frame.motionFrozen, true);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)[\s\S]*animation:none!important/);
  assert.doesNotMatch(css, /@media\(prefers-reduced-motion:reduce\)[^{]*\{[^}]*(auction-factory|auction-building|auction-level|auction-room)[^}]*display:none/);
});

test("unavailable or unknown truth keeps all rooms rendered with truthful unavailable states", () => {
  const model = buildAuctionModel(null, "Canonical sanitized truth is unavailable.");
  const frame = assertFactoryVisible({ safetyLocked: true });
  assert.equal(frame.factoryVisible, true);
  assert.equal(model.condition, "UNAVAILABLE");
  assert.equal(model.nav, null);
  assert.equal(Object.keys(model.rooms).length, 18);
  assert.ok(Object.values(model.rooms).every((state) => state === "unavailable" || state === "locked"));
});

test("Museum Master caption keeps governed identity phrases intact", () => {
  assert.match(app, /<span>GOVERNED READ MODEL<\/span>/);
  assert.match(css, /\.auction-gallery-caption small span\{white-space:nowrap\}/);
});

test("the architectural base style is visible before and without animation", () => {
  assert.match(css, /\.auction-building\{[^}]*clip-path:inset\(0\)/);
  const reveal = css.slice(css.indexOf("@keyframes auction-building-reveal"), css.indexOf("@keyframes auction-evidence-pulse"));
  assert.doesNotMatch(reveal, /clip-path/);
  assert.doesNotMatch(css, /\.is-truth-frozen \.auction-building[^}]*clip-path:inset\(0 100%/);
  assert.match(css, /\.auction-gallery-caption\{[^}]*pointer-events:none/);
  assert.match(factory, /data-testid="auction-factory"/);
  assert.match(factory, /data-testid="auction-max"/);
  assert.match(factory, /data-testid="auction-room"/);
});
