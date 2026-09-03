import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { AUCTION_ROOMS } from "./auctionRegistry.ts";
import { buildAuctionModel } from "./auctionSceneModel.ts";
import { deployedAvailableTruth } from "./livingWallTruthContract.fixture.ts";

const app = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const factory = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./AuctionEdition.css", import.meta.url), "utf8");
const startScript = readFileSync(new URL("../../scripts/start_auction_wall_display.sh", import.meta.url), "utf8");
const stopScript = readFileSync(new URL("../../scripts/stop_auction_wall_display.sh", import.meta.url), "utf8");
const displayConfig = readFileSync(new URL("../../config/auction_wall_display.example.json", import.meta.url), "utf8");
const available = () => ({ source: "/living-wall/truth", fallback: false, data: structuredClone(deployedAvailableTruth) });

test("all 18 rooms have unique architectural identities and wall-readable state labels", () => {
  assert.equal(AUCTION_ROOMS.length, 18);
  assert.equal(new Set(AUCTION_ROOMS.map((room) => room.silhouette)).size, 18);
  assert.ok(AUCTION_ROOMS.every((room) => room.instruments.length >= 3 && room.light && room.idleBehavior));
  assert.match(factory, /data-silhouette=\{room\.silhouette\}/);
  assert.match(factory, /state\.toUpperCase\(\)/);
  for (const room of AUCTION_ROOMS) assert.match(css, new RegExp(`\\.auction-room--${room.id} \\.auction-room__`));
});

test("signature rooms and elevated museum spaces receive distinct close-room art", () => {
  for (const room of ["radar", "research", "committee", "skeptic", "risk", "paper", "evidence", "judgment", "control", "replay", "expansion"]) {
    assert.match(css, new RegExp(`\\.auction-room-modal--${room}`));
  }
  assert.match(factory, /auction-max-walkway/);
  assert.match(app, /auction-case-theater/);
  assert.match(app, /auction-plaque/);
});

test("Museum Master identity, six modes, Case Theater, and Collector Plaque are explicit", () => {
  assert.match(app, /Museum Master 1\.2/);
  for (const mode of ["gallery", "story", "replay", "command", "expansion", "watch"]) assert.match(app, new RegExp(`"${mode}"`));
  assert.match(app, /CASE THEATER \/ READ ONLY/);
  assert.match(app, /IIOS Living Wall — The Auction Edition/);
});

test("ambient motion is governed, receipt motion is quarantined, and unsafe truth freezes", () => {
  const quiet = buildAuctionModel(available(), null);
  assert.deepEqual(quiet.motion, { ambient: true, evidence: false, reason: "AMBIENT_ONLY" });
  const activeFixture = available();
  const data = activeFixture.data as Record<string, unknown>;
  const validation = data.validation as { layers: Record<string, { payload?: object }> };
  validation.layers.factory_telemetry.payload = { recent_events: [{ event_type: "committee_completed", created_at: "2026-09-02T12:00:00Z", case_id: "case-1" }] };
  assert.deepEqual(buildAuctionModel(activeFixture, null).motion, { ambient: true, evidence: true, reason: "VERIFIED_RECEIPT" });
  assert.deepEqual(buildAuctionModel(null, "unavailable").motion, { ambient: false, evidence: false, reason: "FROZEN_UNSAFE" });
  assert.match(factory, /has-evidence-motion/);
  assert.doesNotMatch(css, /has-evidence-motion[^\n]*auction-max-breathe/);
});

test("pause and reduced-motion disable every Museum Master animation", () => {
  assert.match(app, /setPaused\(\(current\) => !current\)/);
  assert.match(css, /\.is-paused \*[^\n]*animation-play-state:paused!important/);
  assert.match(app, /is-truth-frozen/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)[\s\S]*auction-max-walkway/);
});

test("supported display targets retain a wide wall canvas and laptop fallback", () => {
  for (const [width, height] of [[1920, 1080], [2560, 1440], [3440, 1440], [3840, 2160], [1512, 874]]) assert.ok(width / height > 1.6);
  assert.match(css, /@media\(min-width:1800px\)/);
  assert.match(css, /@media\(min-width:3000px\)/);
  assert.match(css, /@media\(max-width:1100px\)/);
  assert.match(css, /@media\(max-width:700px\)/);
  assert.match(css, /\.auction-shell:fullscreen \.auction-gallery\{height:100vh;overflow:hidden\}/);
});

test("Case Theater and plaque share complete accessible dialog behavior", () => {
  assert.match(app, /function AccessibleDialog/);
  assert.match(app, /aria-modal="true" aria-labelledby=\{titleId\} aria-describedby=\{descriptionId\}/);
  assert.match(app, /activateDialog\(\{ dialog, initialFocus, opener: openerRef\.current, background, close/);
  assert.match(app, /requestDialogClose\(close\)/);
});

test("reversible kiosk templates contain no startup installation, credential, or personal path", () => {
  const combined = `${startScript}\n${stopScript}\n${displayConfig}`;
  assert.match(startScript, /open -a Safari/);
  assert.match(stopScript, /Auction wall server stopped/);
  assert.doesNotMatch(combined, /LaunchAgents|launchctl|defaults write|\/Users\/|\/home\/|BEGIN .*PRIVATE KEY|token\s*[=:]|password\s*[=:]|secret\s*[=:]/i);
  assert.equal(JSON.parse(displayConfig).browser.startup_automation_enabled, false);
});
