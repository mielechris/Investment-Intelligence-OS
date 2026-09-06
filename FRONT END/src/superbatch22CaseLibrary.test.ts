import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { linkPromotionReceipts, type FactoryOutputReceipt } from "./museumLiveBinding.ts";

const source = (name: string) => readFileSync(new URL(name, import.meta.url), "utf8");

test("promotion receipts link only through an exact immutable identity", () => {
  const receipt: FactoryOutputReceipt = { id: "r1", timestamp: "2026-09-05T12:00:00Z", module: "RADAR", category: "OPPORTUNITY_PROMOTED_TO_CASE", state: "AUTHENTICATED_RECEIPT", opaqueIdentity: "CASE-1", freshness: "HISTORICAL_RECEIPT", explanation: "bounded" };
  assert.equal(linkPromotionReceipts([receipt], [{ case_id: "CASE-1" }])[0]?.state, "LINKED");
  assert.equal(linkPromotionReceipts([{ ...receipt, opaqueIdentity: null }], [{ case_id: "CASE-1" }])[0]?.reason, "NO_BROWSER_SAFE_CASE_IDENTITY");
  assert.equal(linkPromotionReceipts([{ ...receipt, opaqueIdentity: "CASE-X" }], [{ case_id: "CASE-1" }])[0]?.state, "UNLINKED");
});

test("case and product surfaces are primary, bounded, and responsive", () => {
  const app = source("LivingWallApp.tsx"), cases = source("MuseumCaseLibrary.tsx"), products = source("MobExpansionWing.tsx"), css = source("MobExpansionWing.css");
  assert.match(app, /\["cases", "Cases"\]/); assert.match(app, /Radar · 40 authenticated cases/); assert.match(app, /Evidence · 40 incomplete/); assert.match(app, /Replay · 0 authenticated/);
  assert.match(cases, /Showing \{visible\.length\} of \{cases\.length\}/); assert.match(cases, /No authenticated governed case found/); assert.match(cases, /Promotion receipt linkage/);
  assert.match(products, /Twenty-four directly visible product accounts/); assert.doesNotMatch(products, /\$240,000/); assert.match(products, /Operational paper fund", "\$10,000 SEPARATE/); assert.match(products, /Paper-test-ready products", 0/); assert.match(products, /Research-only products", 11/); assert.match(products, /Incomplete products", 13/); assert.match(products, /AUTHENTIC PRODUCT EVIDENCE REQUIRED/);
  assert.match(css, /\.mew-account-directory\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/); assert.match(css, /max-width:1100px.*\.mew-account-directory.*repeat\(2/s); assert.match(css, /max-width:620px.*\.mew-account-directory.*minmax\(0,1fr\)/s);
});
