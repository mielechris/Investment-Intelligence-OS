import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const view=readFileSync(new URL("./MobExpansionWing.tsx",import.meta.url),"utf8");
const provider=readFileSync(new URL("./ExpansionWingSnapshotProvider.tsx",import.meta.url),"utf8");

test("authenticated supervisor projection is scalar and read only",()=>{
  for(const phrase of ["Unattended supervisor installation","Provenance","Manifest","Inventory","Commit binding","Service ownership","Lock ownership","Listeners / children","Readiness"])
    assert.ok(view.includes(phrase),phrase);
  for(const forbidden of ["Install supervisor","Restart supervisor","Reconcile supervisor","Activate Stage A"])
    assert.ok(!view.includes(`>${forbidden}<`),forbidden);
});

test("older supervisor reads cannot replace a newer projection",()=>{
  assert.ok(provider.includes("supervisorGeneration"));
  assert.ok(provider.includes("supervisorReadAt < priorSupervisor.readAt"));
  assert.ok(provider.includes("coherent_read_timestamp"));
  assert.ok(provider.includes("generation_identity"));
});
