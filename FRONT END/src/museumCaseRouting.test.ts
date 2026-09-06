import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const app=readFileSync(new URL("./LivingWallApp.tsx",import.meta.url),"utf8");
const library=readFileSync(new URL("./MuseumCaseLibrary.tsx",import.meta.url),"utf8");

test("case namespace cannot fall through to Gallery",()=>{
  assert.match(app,/requested\.split\("\/", 1\)\[0\]/);
  assert.match(library,/\^#cases\\\/\(\[\^\/\]\+\)\$/);
  assert.match(library,/#cases\/\$\{encodeURIComponent\(identity\)\}/);
  assert.match(library,/status:"CASE UNAVAILABLE"/);
});

test("case history and focus remain local and bounded",()=>{
  assert.match(library,/history\.pushState\(\{museumMode:"cases",caseId:identity\}/);
  assert.match(library,/addEventListener\("popstate",restoreCase\)/);
  assert.match(library,/addEventListener\("hashchange",restoreCase\)/);
  assert.match(library,/originRef\.current\?\.focus\(\)/);
  assert.doesNotMatch(library,/location\.href|location\.assign|location\.reload/);
});
