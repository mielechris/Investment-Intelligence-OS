import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("./AuctionEdition.css", import.meta.url), "utf8");
const factory = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");

test("desktop, ultrawide, and physical-4K layout targets retain the cinematic canvas", () => {
  const targets = [
    { name: "desktop", width: 1440, height: 900 },
    { name: "ultrawide", width: 3440, height: 1440 },
    { name: "physical-4K", width: 3840, height: 2160 },
  ];
  for (const target of targets) {
    assert.ok(target.width >= 1101, `${target.name} uses the desktop room layout`);
    assert.ok(target.width / target.height >= 1.6, `${target.name} provides a wide cinematic canvas`);
  }
  assert.match(css, /\.auction-gallery\{[^}]*min-height:100svh/);
  assert.match(css, /\.auction-factory\{[^}]*height:calc\(100svh - 112px\)/);
  assert.match(css, /@media\(max-width:1100px\)/);
  assert.match(css, /@media\(max-width:700px\)/);
});

test("print capture keeps an honest 16:9 still-frame rule", () => {
  const printRules = css.slice(css.indexOf("@media print"));
  assert.match(printRules, /\.auction-gallery\{padding:0\}/);
  assert.match(printRules, /\.auction-factory\{height:56\.25vw/);
});

test("art pass composes rooms into one three-level architectural section", () => {
  assert.match(factory, /const levels = \[AUCTION_ROOMS\.slice\(0, 5\), AUCTION_ROOMS\.slice\(5, 10\), AUCTION_ROOMS\.slice\(10\)\]/);
  assert.match(factory, /auction-service-core/);
  assert.match(factory, /auction-evidence-spine/);
  assert.match(factory, /auction-max-walkway/);
  assert.match(factory, /activeRouteIndex >= index \? "is-lit" : ""/);
  assert.match(css, /\.auction-level__rooms\{[^}]*display:grid/);
  assert.match(css, /\.auction-level \.auction-room\{position:relative;inset:auto!important;width:auto!important/);
});

test("presentation mode uses the browser Fullscreen API and retains reduced-motion overrides", () => {
  assert.match(app, /document\.documentElement\.requestFullscreen\(\)/);
  assert.match(app, /document\.exitFullscreen\(\)/);
  assert.match(app, /fullscreenchange/);
  assert.match(css, /\.auction-shell:fullscreen \.auction-factory\{height:100vh\}/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)[\s\S]*\.auction-building\{clip-path:inset\(0\);filter:none\}/);
});

test("close-room art pass preserves dialog semantics while staging architectural interiors", () => {
  assert.match(factory, /auction-room-modal--\$\{room\.id\}/);
  assert.match(factory, /auction-interior-architecture/);
  assert.match(factory, /auction-interior-console/);
  assert.match(css, /\.auction-room-modal>section\{display:grid;grid-template-columns:/);
  for (const room of ["radar", "research", "committee", "skeptic", "risk", "paper"]) {
    assert.match(css, new RegExp(`\\.auction-room-modal--${room}>section`));
  }
});
