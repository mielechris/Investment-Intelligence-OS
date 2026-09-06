import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
const source=(name:string)=>readFileSync(new URL(name,import.meta.url),"utf8");

test("provider source department is complete and keeps the 28-station registry",()=>{
  const component=source("MuseumControlRoom.tsx");
  assert.equal((component.match(/\{ id: "/g)??[]).length,28);
  for(const field of ["Provider","Entitlement","Connection","Last observation","Freshness","Product coverage","Requests","Credits","Failures","Next scheduled check","Activation state","Rollback state"]){assert.match(component,new RegExp(`"${field}"`))}
  assert.match(component,/id: "provider".*section: "listed_security_sources".*scope: "NOT ACTIVATED"/);
});

test("browser control is passive, responsive and hides licensed values",()=>{
  const component=source("MuseumControlRoom.tsx"),css=source("MuseumControlRoom.css"),provider=source("ExpansionWingSnapshotProvider.tsx");
  assert.match(component,/browser_request_authority:false/); assert.match(component,/provider_route:false/);
  assert.doesNotMatch(component,/fetch\([^)]*(provider|financialdatasets)/i);
  assert.match(css,/repeat\(4,minmax\(0,1fr\)\)/); assert.match(css,/max-width:1024px.*repeat\(2/s); assert.match(css,/max-width:620px.*minmax\(0,1fr\)/s);
  assert.match(provider,/const POLL_MS = 15_000/); assert.equal((provider.match(/window\.setTimeout/g)??[]).length,1);
});
