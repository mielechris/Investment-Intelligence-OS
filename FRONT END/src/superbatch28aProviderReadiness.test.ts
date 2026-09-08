import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

const source = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./MobExpansionWing.css", import.meta.url), "utf8");

test("projects scalar readiness without mutation controls or secret selectors", () => {
  assert.match(source, /section\(snapshot, "provider_stage_a_readiness"\)/);
  for (const label of ["Commissioning", "Unattended supervisor", "One-day policy", "Cost contract", "Request plan identities", "Supported and costed", "Blocked identities", "Expected Stage A cost", "Stage A maximum", "Daily hard ceiling", "Credential", "Released credits", "Stage B / C", "Failure category", "Trading authority", "Next gate: owner policy authorization"]) assert.match(source, new RegExp(label));
  assert.doesNotMatch(source, /com\.iios\.expansion-wing\.financial-datasets/);
  assert.doesNotMatch(source, /onClick=\{[^}]*provider|<button[^>]+provider/i);
});
test("wraps boundedly without horizontal overflow", () => {
  assert.match(css, /\.mew-provider-readiness\{min-width:0/);
  assert.match(css, /flex-wrap:wrap/);
  assert.match(css, /overflow-wrap:anywhere/);
});
