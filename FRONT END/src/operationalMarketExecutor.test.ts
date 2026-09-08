import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./MobExpansionWing.tsx", import.meta.url), "utf8");

test("operational execution projection is count-only and read-only", () => {
  for (const label of ["Installation", "Planned", "Dispatched", "Completed", "Failed", "Ambiguous", "Evidence receipts", "Confirmed credits", "Released credits", "Credential accesses", "Stage A", "Stage B", "Stage C"])
    assert.match(source, new RegExp(`\\[\\"${label}\\"`));
  assert.match(source, /Provider bodies, request identities, and credential material never enter the browser/);
  assert.doesNotMatch(source, /executor\.(request_identity|evidence|credential|provider_body)/);
  assert.doesNotMatch(source, /Operational Market Evidence Executor[\s\S]{0,1200}(Activate|Run now|Release credits)/);
});
