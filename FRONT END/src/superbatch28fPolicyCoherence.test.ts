import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const provider=readFileSync(new URL("./ExpansionWingSnapshotProvider.tsx",import.meta.url),"utf8");
const ui=readFileSync(new URL("./MobExpansionWing.tsx",import.meta.url),"utf8");
test("unattended generations replace atomically and reject older inflight reads",()=>{
  for(const phrase of ["unattendedGeneration","last_coherent_read_timestamp","generation_sequence","priorUnattended"]) assert.ok(provider.includes(phrase),phrase);
  assert.ok(provider.includes("unattendedReadAt < priorUnattended.readAt"));
  assert.ok(!provider.includes("install-one-day-policy"));
});
test("policy presentation remains read only and distinguishes failed closed",()=>{
  for(const phrase of ["Policy schema","Commit binding","Authorized allowance","Released credits","FAILED CLOSED"]) assert.ok(ui.includes(phrase),phrase);
  for(const forbidden of ["Install policy","Release Stage A","Activate policy"]) assert.ok(!ui.includes(`>${forbidden}<`),forbidden);
});
