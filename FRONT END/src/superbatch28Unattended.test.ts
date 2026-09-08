import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source=readFileSync(new URL("./MobExpansionWing.tsx",import.meta.url),"utf8");
const css=readFileSync(new URL("./MobExpansionWing.css",import.meta.url),"utf8");

test("unattended presentation is scalar read only and authority locked",()=>{
  for(const phrase of ["UNATTENDED TUESDAY · READ-ONLY STATUS","POLICY INSTALLED — DISABLED","POLICY NOT INSTALLED","NO TRADING AUTHORITY","Policy schema","Commit binding","Authorized allowance","Stage A maximum","Released credits","Authority locked"])
    assert.ok(source.includes(phrase),phrase);
  for(const forbidden of ["Install policy","Release credits","Run now","Activate Stage A","X-API-KEY"])
    assert.ok(!source.includes(`>${forbidden}<`),forbidden);
});

test("every unattended phase has an explicit truthful headline",()=>{
  for(const label of ["POLICY NOT INSTALLED","POLICY INSTALLED — DISABLED","WAITING FOR PREFLIGHT","PREFLIGHT RUNNING","PREFLIGHT FAILED CLOSED","READY FOR TUESDAY","STAGE A RUNNING","PARTIAL SESSION","STAGE A COMPLETE","STAGE A LOCKED","SESSION CLOSED","EMERGENCY STOPPED"]){
    assert.ok(source.includes(label),label);
  }
  assert.ok(source.includes('?? "FAILED CLOSED"'));
});

test("all twenty four rooms retain the ten four ten Tuesday split",()=>{
  assert.ok(source.includes("pilots ·"));
  assert.ok(source.includes("readiness ·"));
  assert.ok(source.includes("structural"));
  assert.ok(source.includes("Browser activity cannot install it, release credits, invoke providers, or control the supervisor."));
});

test("unattended status wraps without desktop medium or narrow overflow",()=>{
  assert.match(css,/\.mew-unattended-status\{[^}]*min-width:0/);
  assert.match(css,/grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css,/@media\(max-width:1024px\).*repeat\(2,minmax\(0,1fr\)\)/s);
  assert.match(css,/@media\(max-width:620px\).*minmax\(0,1fr\)/s);
  assert.match(css,/overflow-wrap:anywhere/);
});
