/// <reference types="node" />
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const control = readFileSync(new URL("./MuseumControlRoom.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./MuseumControlRoom.css", import.meta.url), "utf8");
const wall = readFileSync(new URL("./LivingWallApp.tsx", import.meta.url), "utf8");
const scene = readFileSync(new URL("./auctionSceneModel.ts", import.meta.url), "utf8");
const provider = readFileSync(new URL("./ExpansionWingSnapshotProvider.tsx", import.meta.url), "utf8");

test("complete Control Room has exactly 28 non-competing governed stations", () => {
  const ids = [...control.matchAll(/\{ id: "([^"]+)", title:/g)].map((match) => match[1]);
  assert.equal(ids.length, 28);
  assert.equal(new Set(ids).size, 28);
  for (const label of ["Executive Factory Status", "9H Independent Validation", "9I Browser-Safe Shadow State", "Candidate Conveyor", "Professional Research Observatory", "Post-Close Audit", "Security and Authority Locks"]) assert.match(control, new RegExp(label));
  assert.match(wall, /<MuseumControlRoom/);
});

test("every station exposes the complete truth vocabulary and human summary contract", () => {
  for (const label of ["State", "Evidence timestamp", "Effective timestamp", "Freshness", "Provenance", "Eligibility", "Blocker", "Next observation", "Technical details"]) assert.match(control, new RegExp(label));
  for (const state of ["CURRENT", "AVAILABLE", "AVAILABLE_EMPTY", "STALE", "INCOMPLETE", "UNAVAILABLE", "FAILED_CLOSED", "NOT_ACTIVATED", "RESEARCH_ONLY_UNPRICEABLE", "INSUFFICIENT_SAMPLE"]) assert.match(control + css, new RegExp(state.toLowerCase().replaceAll("_", "-") + "|" + state));
});

test("quiet Gallery separates ambient presentation from evidence movement", () => {
  assert.match(wall, /AMBIENT PRESENTATION/);
  assert.match(wall, /No candidate, trade, position, order, recommendation, endorsement, profit, or provider connection is implied/);
  assert.match(scene, /evidence: healthy && active !== null/);
  assert.match(scene, /reason: healthy && active \? "VERIFIED_RECEIPT" : "AMBIENT_ONLY"/);
});

test("browser retains one polling owner and no publication or mutation route", () => {
  assert.equal((provider.match(/fetch\(/g) ?? []).length, 1);
  assert.doesNotMatch(control + wall, /fetch\(|method:\s*"(?:POST|PUT|PATCH|DELETE)"|publish\(|createOrder|ledger\/write|broker\/connect/);
  assert.match(control, /publisherControl \? "UNSAFE" : "FALSE"/);
});

test("responsive control room contains overflow, supports focus, and honors reduced motion", () => {
  for (const marker of ["min-width:0", "overflow-x:clip", "grid-template-columns:repeat(3", "max-width:1180px", "max-width:620px", "focus-visible", "scroll-margin-top", "prefers-reduced-motion:reduce"]) assert.match(css, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("visual repair establishes executive hierarchy and eight governed departments", () => {
  for (const label of ["WHAT THE FACTORY IS DOING NOW", "Factory operating state", "Market session", "Protected-service health", "Candidate Conveyor", "Operational paper NAV / cash", "Primary blockers", "Next scheduled factory action"]) assert.match(control, new RegExp(label));
  for (const department of ["Market and Pipeline", "Validation and Learning", "Research and Professional Intelligence", "Committee and Risk", "Products, Methods and Sleeves", "Projection and Provider Infrastructure", "Evidence and Audit", "Security and Authority"]) assert.match(control, new RegExp(department));
  for (const summary of ["No authenticated source report received", "Waiting for the next governed observation", "Optional source is not connected", "Evidence rejected by the integrity gate"]) assert.match(control, new RegExp(summary));
  assert.match(control, /exact raw state/);
});

test("living Gallery makes bounded ambient work legible without moving evidence", () => {
  const factory = readFileSync(new URL("./AuctionFactory.tsx", import.meta.url), "utf8");
  const edition = readFileSync(new URL("./AuctionEdition.css", import.meta.url), "utf8");
  for (const label of ["Ambient factory activity", "Evidence-driven case movement", "Market closed", "Failed closed", "AMBIENT ONLY · CASE ROUTE FROZEN"]) assert.match(factory, new RegExp(label));
  assert.match(edition, /auction-duty-cue/);
  assert.match(edition, /prefers-reduced-motion:reduce/);
  assert.match(wall, /No authenticated replay is available/);
  assert.match(wall, /Historical marker · valid time · immutable lineage · sanitized provenance/);
  assert.match(wall, /Return to Gallery/);
  assert.match(wall, /Open Control Room/);
});
