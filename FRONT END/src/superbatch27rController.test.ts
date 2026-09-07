import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./MobExpansionWing.css", import.meta.url), "utf8");

test("schema version and server-issued provenance independently control presentation", () => {
  for (const phrase of ["controller_status_provenance", "AUTHENTIC_OPERATIONAL_STATE", "AUTHENTIC CONTROLLER STATUS",
    "OPERATIONAL V2 · DISABLED", "MIGRATION COMPLETED · CONTROLLER NOT ACTIVATED", "iios-tuesday-controller-state-v1",
    "NOT PERFORMED", "SYNTHETIC_FIXTURE_NON_LIVE", "FUTURE REVIEW — NOT OPERATIONAL",
    "iios-tuesday-controller-state-v2", "SIMULATED / REHEARSED — NOT OPERATIONAL", "Released credits", "Authority"])
    assert.match(source, new RegExp(phrase));
  assert.doesNotMatch(source, /controllerV2 \? "SYNTHETIC_FIXTURE_NON_LIVE"/);
  assert.doesNotMatch(source, /controllerV2 \? "FUTURE REVIEW — NOT OPERATIONAL"/);
  assert.match(source, /controllerAuthentic \? "AUTHENTIC CONTROLLER STATUS"/);
  assert.match(source, /controllerSynthetic \? "FUTURE REVIEW — NOT OPERATIONAL"/);
  assert.match(source, /"CONTROLLER STATUS UNAVAILABLE"/);
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
  assert.match(source, /aria-label="Controller status provenance"/);
});
