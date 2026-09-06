/// <reference types="node" />
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./LivingWallGalleryStatus.tsx", import.meta.url), "utf8");

test("Gallery status remains a read-only truthful presentation", () => {
  assert.match(source, /FACTORY CONDITION/);
  assert.match(source, /MARKET VALIDATION/);
  assert.match(source, /PAPER NAV/);
  assert.match(source, /LIVE EXECUTION/);
  assert.match(source, /FALSE/);
  assert.doesNotMatch(source, /fetch\(|POST|PUT|PATCH|DELETE/);
});
/// <reference types="node" />
