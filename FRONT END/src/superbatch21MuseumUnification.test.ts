/// <reference types="node" />
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
const wall = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const main = readFileSync(new URL("./main.tsx", import.meta.url), "utf8");
const provider = readFileSync(new URL("./ExpansionWingSnapshotProvider.tsx", import.meta.url), "utf8");
const registry = readFileSync(new URL("./auctionRegistry.ts", import.meta.url), "utf8");
const expansion = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");
const factory = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
const adapter = readFileSync(new URL("./TruthSourceAdapter.ts", import.meta.url), "utf8");
const vite = readFileSync(new URL("../vite.config.ts", import.meta.url), "utf8");

test("Museum Master is the unified factory root with six destinations", () => {
  assert.match(main, /<SelectedApp/);
  assert.match(vite, /unified \? 'src\/LivingWallApp\.tsx'/);
  for (const label of ["Gallery", "Story", "Replay", "Command", "Expansion Wing", "Factory Watch"]) assert.match(wall, new RegExp(`"${label}"`));
  assert.match(wall, /MUSEUM MASTER 1\.2/);
});

test("Museum display controls remain bounded and accessible", () => {
  for (const label of ["Resume Scene", "Wall Art Mode", "Enter Full Screen", "Brightness:", "Collector Plaque", "Sound Muted"]) assert.match(wall, new RegExp(label));
  assert.match(wall, /requestFullscreen/);
  assert.match(wall, /prefers-reduced-motion/);
  assert.match(wall, /button disabled/);
});

test("original architecture and modern research inventory coexist", () => {
  assert.equal((registry.match(/id: "/g) ?? []).length, 18);
  assert.match(expansion, /export const PRODUCT_DESKS/);
  assert.match(expansion, /export const METHOD_DESKS/);
  assert.match(wall, /<MobExpansionWing/);
  assert.match(factory, /MAX’S WALKWAY|MAX'S WALKWAY/);
});

test("one provider owns polling and the Museum shell never publishes", () => {
  assert.equal((provider.match(/15_000/g) ?? []).length >= 1, true);
  assert.doesNotMatch(wall, /fetch\(|loadFactoryTruth|method:\s*"(?:POST|PUT|PATCH|DELETE)"/);
  assert.match(wall, /publisherControl/);
  assert.match(adapter, /direct_ledger_access: false/);
  assert.match(adapter, /trade_execution_permission: false/);
  assert.match(adapter, /live_execution: false/);
});

test("aggregate counts cannot become movement identities", () => {
  assert.match(adapter, /Array\.isArray\(conveyor\.candidates\)/);
  assert.match(adapter, /candidate_id/);
  assert.match(adapter, /discovery_timestamp/);
  assert.match(adapter, /connection === "CURRENT"/);
});
/// <reference types="node" />
