/// <reference types="node" />
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const config = JSON.parse(readFileSync(new URL("../../config/iios_browser_entrypoint.json", import.meta.url), "utf8"));
const start = readFileSync(new URL("../../scripts/start_auction_wall_display.sh", import.meta.url), "utf8");
const stop = readFileSync(new URL("../../scripts/stop_auction_wall_display.sh", import.meta.url), "utf8");
const wall = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const expansion = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");
const provider = readFileSync(new URL("./ExpansionWingSnapshotProvider.tsx", import.meta.url), "utf8");
const manual = readFileSync(new URL("../../DOCS/IIOS_FACTORY_DEVELOPER_OPERATIONS_MANUAL.md", import.meta.url), "utf8");
const main = readFileSync(new URL("./main.tsx", import.meta.url), "utf8");
const vite = readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8");

test("exactly one canonical owner-facing browser is defined", () => {
  assert.equal(config.canonical_url, "http://127.0.0.1:5176/");
  assert.equal(config.user_facing_frontend_count, 1);
  assert.equal(config.expected_identity, "THE AUCTION EDITION · MUSEUM MASTER 1.2");
  assert.deepEqual(config.internal_diagnostics, { "5177": "INTERNAL_DIAGNOSTIC_ONLY", "5185": "INTERNAL_DIAGNOSTIC_ONLY" });
  assert.deepEqual(config.development_frontends, { "5184": "DEVELOPMENT_ONLY", "5186": "DEVELOPMENT_ONLY" });
});

test("owner startup verifies but never starts a competing frontend", () => {
  assert.match(start, /display_url="http:\/\/127\.0\.0\.1:5176\/"/);
  assert.match(start, /--open/);
  assert.match(start, /CANONICAL_MUSEUM_IDENTITY_MISMATCH/);
  assert.doesNotMatch(start, /npm|vite|5173|display_url=.*\$\{1/);
  assert.doesNotMatch(start, /127\.0\.0\.1:(?:5177|5184|5185|5186|49341|49342|5234)\/?["']/);
  assert.doesNotMatch(stop, /kill|launchctl|rm /);
});

test("all owner navigation stays inside the Museum hash router", () => {
  for (const label of ["Gallery", "Story", "Replay", "Command", "Cases", "Expansion Wing", "Factory Watch"]) assert.match(wall, new RegExp(label));
  assert.match(wall, /window\.history\.pushState/);
  assert.doesNotMatch(wall, /https?:\/\/|window\.location\.(?:assign|replace)|window\.open/);
});

test("product selection stays in the Expansion Wing namespace", () => {
  assert.match(expansion, /#expansion\/product\/\$\{encodeURIComponent\(hash\)\}/);
  assert.match(expansion, /museumMode: "expansion", productId: hash/);
  assert.match(expansion, /\^#expansion\\\/product\\\/\(\[\^\/\]\+\)\$/);
  assert.doesNotMatch(expansion, /#product-/);
  assert.doesNotMatch(expansion, /new HashChangeEvent/);
});

test("mounted Museum polling uses same-origin read-only compositor routes", () => {
  assert.match(provider, /const EXPANSION_PATH = "\/expansion-wing\/snapshot"/);
  assert.match(provider, /const CAPABILITIES_ENDPOINT = "\/living\/overview"/);
  assert.equal((provider.match(/fetch\(/g) ?? []).length, 1);
  assert.doesNotMatch(provider + wall, /127\.0\.0\.1:8002|method:\s*"(?:POST|PUT|PATCH|DELETE)"|publish\(|provider.*request|controller.*activate/i);
});

test("production root selection excludes dormant legacy applications", () => {
  assert.match(main, /virtual:iios-selected-app/);
  assert.doesNotMatch(main, /PaperFundOperationsShell|\.\/ExpansionWing\.tsx/);
  assert.match(vite, /unified \? 'src\/LivingWallApp\.tsx'/);
  assert.match(vite, /virtual:iios-selected-app/);
});

test("operations manual names the only owner URL and legacy warning", () => {
  assert.match(manual, /CANONICAL IIOS ENTRYPOINT/);
  assert.match(manual, /http:\/\/127\.0\.0\.1:5176\//);
  assert.match(manual, /OPERATIONS FEED\s+OFFLINE/);
});
