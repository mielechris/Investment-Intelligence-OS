/// <reference types="node" />
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component=readFileSync(new URL("./MobExpansionWing.tsx",import.meta.url),"utf8");
const css=readFileSync(new URL("./MobExpansionWing.css",import.meta.url),"utf8");

test("whole factory counts and staged ceiling are explicit",()=>{
  assert.match(component,/24 rooms · 16 methods · staged 200-credit hard ceiling/);
  assert.match(component,/ceiling: 100/); assert.match(component,/ceiling: 50/);
  assert.match(component,/U\.S\. Mid-Cap Equities/); assert.match(component,/Emerging-Market Equities/);
  assert.match(component,/OPERATIONAL RELEASE ZERO/); assert.match(component,/Released now<\/dt><dd>0/);
  assert.match(component,/24 of 24 product rooms participate/); assert.match(component,/Operational trading rooms<\/dt><dd>0/);
});
test("plan remains read only and distinct from installed v1 controller",()=>{
  assert.match(component,/Automatic release<\/dt><dd>Prohibited/); assert.match(component,/Browser invocation<\/dt><dd>Prohibited/);
  assert.match(component,/10 LIVE EVIDENCE ELIGIBLE · 4 AWAITING SUPPORTED IDENTITY · 10 STRUCTURAL FAIL CLOSED/);
  assert.match(component,/10 Live-Evidence Pilots/); assert.match(component,/4 Listed-Equity Source-Readiness Rooms/); assert.match(component,/10 Specialized Structural Test Rooms/);
  assert.match(component,/Twenty-four product rooms participate in Tuesday testing across ten live-evidence pilots, four listed-equity source-readiness rooms, and ten specialized structural test rooms\./);
  assert.match(component,/Aggregate scanner counts cannot create candidates/);
  assert.doesNotMatch(component,/Twenty-four directly visible product accounts are grouped into ten Tuesday pilots and fourteen future source waves\./);
  assert.doesNotMatch(component,/14 Rooms — Not Available for Tuesday/);
  assert.doesNotMatch(component,/fetch\(|XMLHttpRequest|provider-control|controller-control/);
});
test("responsive stage cards are overflow safe",()=>{
  assert.match(css,/\.mew-pilot-directory\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)\}/);
  assert.match(css,/@media\(max-width:1100px\)\{\.mew-pilot-directory,\.mew-future-directory\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)\}\}/);
  assert.match(css,/@media\(max-width:620px\)\{\.mew-pilot-directory,\.mew-future-directory\{grid-template-columns:minmax\(0,1fr\)\}\}/);
  assert.match(css,/mew-credit-stages[^}]*grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css,/mew-credit-stages article\{min-width:0/);
  assert.match(css,/@media\(max-width:900px\)/); assert.match(css,/@media\(max-width:520px\)/);
  assert.match(css,/mew-readiness-directory b[^}]*#f1d497/); assert.match(css,/mew-structural-directory small[^}]*#c3b7a0/);
});
