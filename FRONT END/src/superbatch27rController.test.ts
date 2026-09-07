import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./MobExpansionWing.css", import.meta.url), "utf8");

test("authentic v1 and synthetic future v2 are unambiguous", () => {
  for (const phrase of ["AUTHENTIC CURRENT OPERATIONAL STATE", "iios-tuesday-controller-state-v1", "NOT PERFORMED",
    "SYNTHETIC_FIXTURE_NON_LIVE", "FUTURE REVIEW — NOT OPERATIONAL", "iios-tuesday-controller-state-v2",
    "NOT OPERATIONAL — REVIEW FIXTURE ONLY", "Released credits", "Authority"])
    assert.match(source, new RegExp(phrase));
});

test("future v2 presents the exact locked staged contract", () => {
  assert.match(source, /Draft 50 · Maximum 100 · Locked \/ not released/);
  assert.match(source, /Stage B[\s\S]*Maximum 50 · Locked/);
  assert.match(source, /Stage C[\s\S]*Maximum 50 · Locked/);
  assert.match(css, /\[data-controller-version="v2"\] \.mew-tuesday-hero\{display:none\}/);
});

test("controller cards wrap at three responsive widths", () => {
  assert.match(css, /repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css, /repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css, /overflow-wrap:anywhere/);
  assert.match(source, /aria-label="Authenticated controller version"/);
});
