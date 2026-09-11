import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import postcss from 'postcss';
import { boundedNavigation, escapeLayer, selectedOpener, selectionHistoryAction } from './northstarNavigation.ts';
import { northstarFixture } from './northstarSession.fixture.ts';
import { factoryCatalog, validFactory } from './truthSpineFactoryView.ts';
import { AUCTION_ROOMS } from './auctionRegistry.ts';
import { sessionPhases } from './truthSpineSessionView.ts';
import { admitProjection, ageProjection, canonical, contentHash, emptyNorthstar, retainedFailure, observeNorthstar, stationRows, northstarFloorOutputs } from './northstarSession.ts';
const now = Date.parse('2026-09-11T13:30:00Z');
const source = (name: string) => readFileSync(new URL(name, import.meta.url), 'utf8');
test('historical admission binds package identity without relaxing fixture or freshness contracts',async()=>{
  const x=await northstarFixture(now),f=x.factory!;
  x.schema='iios-historical-northstar-browser-v2';x.phase='SESSION_CLOSED';
  x.scope='HISTORICAL_REPLAY_NOT_CURRENT_MARKET';f.phase=x.phase;
  for(const row of [...f.rooms,...f.agents,...f.governance,...f.routes,...f.history,...f.subsystems,f.day_trading])row.phase=x.phase;
  f.content_hash=await contentHash(f as unknown as Record<string,unknown>);
  const lineage={schema:'iios-northstar-package-binding-v1',source_commit:'b'.repeat(40),
    package_hash:'1'.repeat(64),package_generation:'2'.repeat(64),runtime_hash:'3'.repeat(64),frontend_hash:'4'.repeat(64),
    admission_hash:'5'.repeat(64),generation_hash:x.source_generation!,initial_cycle_hash:'6'.repeat(64),
    owner_manifest_hash:'7'.repeat(64),completion_hash:'8'.repeat(64),l7_hash:'9'.repeat(64),l8_hash:'a'.repeat(64),
    backend_instance_hash:'e'.repeat(64),common_watermark:'2020-01-02T00:00:00Z',classification:'HISTORICAL_REPLAY',
    source_cycle:x.source_cycle!,projection_hash:f.content_hash};
  const historical={...x,lineage,owners:{...x.owners,backend_owner:lineage.backend_instance_hash}};
  const admitted=await admitProjection(historical,null,now);
  assert.equal(admitted.lineage?.common_watermark,lineage.common_watermark);
  for(const key of ['package_hash','runtime_hash','frontend_hash','admission_hash'])
    await assert.rejects(admitProjection({...historical,lineage:{...lineage,[key]:'c'.repeat(64)}},admitted,now),/PACKAGE_INSTANCE_REPLACED/);
  await assert.rejects(admitProjection(historical,null,now+15001));
  await assert.rejects(admitProjection({...historical,lineage:{...lineage,projection_hash:'c'.repeat(64)}},null,now));
});
test('Northstar validates the complete canonical projection without a legacy adapter', async () => {
  const x = await northstarFixture(now); const result = await admitProjection(x,null,now);
  assert.deepEqual(result,x); assert.notEqual(result,x);
  assert.equal(result.factory!.rooms.length,24); assert.equal(result.factory!.agents.length,8);
});
test('canonical bytes match Python ASCII sorted-key encoding', () => {
  assert.equal(canonical({z:'·',a:{b:1,a:false}}),'{"a":{"a":false,"b":1},"z":"\\u00b7"}\n');
});
test('malformed incomplete stale and identity-mismatched projections are rejected', async () => {
  type Fixture = Awaited<ReturnType<typeof northstarFixture>>;
  for (const mutate of [(x: Fixture)=>{x.factory!.rooms.pop()},(x: Fixture)=>{x.factory!.agents[0].generation_id='0'.repeat(64)},
    (x: Fixture)=>{x.factory!.day_trading.paper_authority=true},(x: Fixture)=>{x.factory!.routes[0].enabled=true},
    (x: Fixture)=>{x.factory!.rooms[0].candidate_count=25},(x: Fixture)=>{x.factory!.content_hash='f'.repeat(64)},
    (x: Fixture)=>{x.published_at=new Date(now-15001).toISOString()},(x: Fixture)=>{x.source_cycle_generated_at=new Date(now-900001).toISOString()},
    (x: Fixture)=>{x.capture_status='STALE'}]) {
    const x=await northstarFixture(now); mutate(x); await assert.rejects(admitProjection(x,null,now));
  }
  for (const x of [null,{},[]]) await assert.rejects(admitProjection(x,null,now));
});
test('session replacement or watermark regression cannot be admitted', async () => {
  const x=await northstarFixture(now); const prior=structuredClone(x); prior.session='another';
  await assert.rejects(admitProjection(x,prior,now)); prior.session=x.session; prior.watermark.count=1;
  await assert.rejects(admitProjection(x,prior,now));
});
test('unknown nested fields cannot leak through metadata disclosures', async () => {
  for (const target of ['top','row','activity','paper']) {
    const x=await northstarFixture(now);
    const object = target==='top' ? x : target==='row' ? x.factory!.rooms[0] : target==='activity' ? x.factory!.rooms[0].activity_counts : x.factory!.day_trading.paper;
    Object.assign(object as object,{unreviewed_field:'NOT_BROWSER_SAFE'});
    await assert.rejects(admitProjection(x,null,now));
  }
});
test('temporary failure retains the last verified immutable record and expires visibly', async () => {
  const view=await northstarFixture(now); const s={view,status:'CURRENT' as const,reason:'VERIFIED'};
  assert.equal(retainedFailure(s).view,view); assert.equal(retainedFailure(s).status,'STALE');
  assert.equal(ageProjection(s,now+15001).status,'STALE'); assert.equal(retainedFailure(emptyNorthstar).status,'UNAVAILABLE');
});
test('one polling owner, no fallback, bounded body, abort and cleanup', async () => {
  const calls: string[]=[]; const values: string[]=[]; const x=await northstarFixture(now);
  const fake: typeof fetch=async (input,options)=>{calls.push(String(input));assert.equal(options?.credentials,'omit');
    assert.equal(options?.redirect,'error');return new Response(JSON.stringify(x),{headers:{'content-type':'application/json'}});};
  const stop=observeNorthstar(s=>values.push(s.status),fake,()=>now);
  await new Promise(resolve=>setTimeout(resolve,50)); stop();
  assert.deepEqual(calls,['/truth-spine/full-session']); assert.ok(values.includes('CURRENT'));
  const text=source('./northstarSession.ts'); assert.equal((text.match(/setTimeout\(poll/g)??[]).length,1);
  assert.doesNotMatch(text,/living\/overview|expansion-wing\/snapshot|fixtures\/|127\.0\.0\.1|method:\s*['"]POST/);
  assert.match(text,/1_048_576/); assert.match(text,/abort\?\.abort/);
});
test('wrong HTTP media type and oversized bodies never admit an update', async () => {
  for (const response of [new Response('{}',{headers:{'content-type':'text/html'}}),new Response(' '.repeat(1_048_577),{headers:{'content-type':'application/json'}})]) {
    const states: string[]=[]; const stop=observeNorthstar(s=>states.push(s.status),async()=>response,()=>now);
    await new Promise(resolve=>setTimeout(resolve,30)); stop(); assert.ok(states.length); assert.ok(states.every(s=>s==='UNAVAILABLE'));
  }
});
test('all required groups retain identity, unknown values and zero authority',async()=>{
  const f=(await northstarFixture(now)).factory!;
  assert.equal(new Set(f.rooms.map(r=>r.id)).size,24); assert.equal(f.governance.length,3); assert.equal(f.routes.length,10);
  for(const row of [...f.rooms,...f.agents,...f.governance,...f.routes,f.day_trading]) assert.ok(Object.values(row.authority).every(v=>v===false));
  assert.ok(f.routes.every(r=>r.credential_presence==='UNKNOWN')); assert.equal(f.day_trading.order_allowance,0);
  assert.ok(f.rooms.every(r=>r.activity_counts.current_invocations===null&&r.candidate_count===null));
  assert.equal(stationRows(f,'radar')[0].id,'9E'); assert.deepEqual(stationRows(null,'radar'),[]);
});
test('dedicated root mounts only full-session owner, not permanent provider',()=>{
  const s=source('./NorthstarFullSession.tsx'); assert.equal((s.match(/<NorthstarSessionProvider>/g)??[]).length,1);
  assert.doesNotMatch(s,/ExpansionWingSnapshotProvider|fixture|StrictMode/); assert.match(s,/fullSession/);
});
test('existing shell navigation and factory artwork are used, not engineering preview',()=>{
  const s=source('./LivingWallApp.tsx').split('export function NorthstarLivingWall()')[1];
  for(const component of ['NorthstarNavigation','NorthstarAuctionFactory','NorthstarRoomView','NorthstarControlRoom','NorthstarCaseLibrary','NorthstarExpansionWing']) assert.ok(s.includes(`<${component}`));
  assert.doesNotMatch(s,/TruthSpineIntegrationPreview|adaptExpansionSnapshot|40 authenticated|35 cases/);
  assert.match(s,/NARRATIVE PRESENTATION ONLY/); assert.match(s,/NO_CURRENT_CASE_DOSSIER/);
  assert.match(s,/boundedNavigation/); assert.doesNotMatch(s,/location\.href\s*=|location\.reload/);
});
test('required panels are reachable, full width and not hidden at narrow sizes',()=>{
  const s=source('./NorthstarPanels.tsx'); for(const group of ['rooms','agents','governance','history','routes','subsystems'])assert.ok(s.includes(group));
  for(const phrase of ['Day Trading','LOCKED','Original evidence','Separate Universe','Incidents','Authority','UNAVAILABLE'])assert.ok(s.includes(phrase));
  const css=source('./NorthstarFullSession.css');assert.match(css,/repeat\(3, minmax\(0, 1fr\)\)/);assert.match(css,/repeat\(2, minmax\(0, 1fr\)\)/);assert.match(css,/max-width: 700px/);
  assert.doesNotMatch(css,/overflow:\s*hidden|display:\s*none|text-overflow/);
});
test('permanent and engineering entrypoints remain independent',()=>{
  assert.match(source('../vite.config.ts'),/northstar-session\.html/);assert.match(source('../vite.config.ts'),/publicDir: false/);
  assert.match(source('./main.tsx'),/<ExpansionWingSnapshotProvider>/);assert.doesNotMatch(source('./main.tsx'),/NorthstarSession/);
  assert.match(source('./TruthSpineIntegrationPreview.tsx'),/truth-spine\/full-session/);
});
test('architectural stations never consume legacy output defaults or invent zero activity', async()=>{
  const view=await northstarFixture(now);
  const outputs=northstarFloorOutputs({view,status:'CURRENT',reason:'VERIFIED'});
  assert.equal(Object.keys(outputs).length,18);
  for(const output of Object.values(outputs)) { assert.equal(output.source,'/truth-spine/full-session');assert.equal(output.count,null);assert.equal(output.state,'UNAVAILABLE'); }
  const floor=source('./AuctionFactory.tsx').split('export function NorthstarAuctionFactory(')[1].split('function Room(')[0];
  assert.doesNotMatch(floor,/roomOutput\(/);
  assert.doesNotMatch(source('./AuctionFactory.tsx').split('export function NorthstarRoomView(')[1],/roomOutput\(/);
});
test('Gallery exposes the existing 24 governed identities without changing architectural stations',async()=>{
  const shell=source('./LivingWallApp.tsx').split('export function NorthstarLivingWall()')[1];
  assert.match(shell,/mode === 'gallery'.*<NorthstarGroup group="rooms"/);
  const rows=(await northstarFixture(now)).factory!.rooms;
  assert.equal(rows.length,24); assert.equal(new Set(rows.map(r=>r.id)).size,24);
  assert.equal(new Set(rows.map(r=>r.name)).size,24);
});
test('required-text detector detects true clipping without treating decorative scroll bounds as text',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  const geometry=runner.split('TEXT_GEOMETRY = r"""')[1].split('"""')[0];
  const outside=runInNewContext(geometry+';outside') as (r:object,b:object,x:boolean,y:boolean)=>boolean;
  const box={space:'viewport-css-px',left:0,right:100,top:0,bottom:40};
  assert.equal(outside({...box,right:101,bottom:39},box,true,true),false);
  assert.equal(outside({...box,right:150,bottom:39},box,true,false),true);
  assert.equal(outside({...box,right:80,bottom:55},box,false,true),true);
  assert.equal(outside({...box,right:150,bottom:55},box,false,false),false);
  assert.match(geometry,/createTreeWalker\(root, NodeFilter.SHOW_TEXT\)/);
  assert.match(geometry,/closest\('\[aria-hidden="true"\]'\)/);
  assert.match(geometry,/range\.getClientRects/);
  assert.match(geometry,/\['hidden','clip'\]\.includes\(s.overflowX\)/);
  assert.doesNotMatch(geometry,/scrollWidth|clientWidth/);
});
test('Safari detector regression probes cover clipped nested text, long names, decorations and actual overlap',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  for(const name of ['realClipping','decorative','longNestedName','realOverlap','collapsed'])assert.ok(runner.includes('cases.'+name));
  assert.match(runner,/DETECTOR_REGRESSION_FAILED/);assert.match(runner,/ACCESSIBLE_ROOM_IDENTITY_MISMATCH/);
  assert.match(runner,/ESCAPE_FOCUS_FAILED/);assert.match(runner,/POLLING_OWNER_INTERVAL_FAILED/);
  const css=source('./NorthstarFullSession.css');assert.match(css,/:focus-visible.*outline: 3px/);
  assert.match(css,/white-space: normal/);assert.match(css,/overflow-wrap: anywhere/);
});
test('Escape closes exactly the focused top layer and ignores malformed, repeated or unrelated keys',()=>{
  for(const key of ['Escape','Esc']) {
    assert.equal(escapeLayer({type:'keydown',key},true,true),'disclosure');
    assert.equal(escapeLayer({type:'keydown',key},true,false),'panel');
    assert.equal(escapeLayer({type:'keydown',key},false,true),'ignore');
  }
  for(const event of [{},{type:'keyup',key:'Escape'},{type:'keydown',key:27},{type:'keydown',key:'Enter'},
    {type:'keydown',key:'U+001B'},...['repeat','isComposing','defaultPrevented','altKey','ctrlKey','metaKey','shiftKey'].map(flag=>({type:'keydown',key:'Escape',[flag]:true}))])
    assert.equal(escapeLayer(event,true,false),'ignore');
});
test('owned selection close traverses its entry, rather than pushing a second entry per cycle',()=>{
  const hash='#cases/coverage/history/l7';
  for(let i=0;i<200;i++) assert.equal(selectionHistoryAction({northstarSelection:{group:'history',id:'l7',hash}},'history','l7',hash),'back');
  for(const state of [null,{}, {northstarSelection:null},{northstarSelection:{group:'rooms',id:'l7',hash}},
    {northstarSelection:{group:'history',id:'l8',hash}}]) assert.equal(selectionHistoryAction(state,'history','l7',hash),'replace');
  assert.equal(selectionHistoryAction({northstarSelection:{group:'history',id:'l7',hash}},'history','l7','#cases'),'replace');
});
test('close is idempotent, clears state before history effects, and restores the exact opener after rendering',()=>{
  const panel=source('./NorthstarPanels.tsx');const close=panel.split('const close = () => {')[1].split('const select =')[0];
  assert.match(close,/if \(!id\) return/);assert.doesNotMatch(close,/pushState/);
  assert.ok(close.indexOf('setSelected(null)')<close.indexOf('history.back()'));
  assert.match(close,/hash.endsWith/); assert.match(close,/catch \{ setRouteError\(true\)/);
  assert.match(panel,/requestAnimationFrame/);assert.match(panel,/cancelAnimationFrame/);
  assert.match(panel,/data-northstar-opener/);assert.match(panel,/aria-controls/);assert.match(panel,/role="region"/);
});
test('one scoped React keyboard handler survives rerender without global listeners or unrelated-layer closure',()=>{
  const panel=source('./NorthstarPanels.tsx');
  assert.equal((panel.match(/onKeyDown=/g)??[]).length,1);
  assert.doesNotMatch(panel,/addEventListener\(['"]keydown/);
  assert.match(panel,/e.currentTarget.contains\(target\)/);assert.match(panel,/e.currentTarget.contains\(detail\)/);
  assert.match(panel,/e.preventDefault\(\); e.stopPropagation\(\)/);
  assert.match(panel,/action === 'disclosure'/);assert.match(panel,/else close\(\)/);
  assert.match(panel,/<button onClick=\{close\}>/);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  for(const gate of ['NESTED_ESCAPE_FOCUS_FAILED','ESCAPE_FOCUS_FAILED','CLOSED_ESCAPE_MUTATED_STATE'])assert.ok(runner.includes(gate));
  assert.match(runner,/wait_for\("return !document.querySelector\('\.northstar-selected'\)"\)/);
});
test('Northstar floor explanations have content-driven height at every breakpoint',()=>{
  const css=source('./NorthstarFullSession.css');
  const explanation=css.match(/\.northstar-full-session \.auction-room__output small \{([^}]+)\}/)![1];
  for(const rule of ['height: auto','max-height: none','overflow: visible','white-space: normal','overflow-wrap: anywhere','font-size: .875rem','line-height: 1.5']) assert.ok(explanation.includes(rule));
  assert.doesNotMatch(explanation,/line-clamp|text-overflow|display:\s*none|opacity|mask|height:\s*\d+(px|em)/);
  assert.match(css,/\.auction-level \.auction-room \{ height: auto !important;[^}]+display: flex/);
  assert.match(css,/\.auction-level__rooms \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); gap: 1rem; padding: .5rem/);
  assert.match(css,/max-width: 1100px[^\n]+\.auction-level__rooms[^\n]+repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css,/max-width: 700px[^}]+\.auction-level__rooms[^}]+grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css,/\.auction-room__output \{ display: grid/);
});
test('all governed rooms keep complete names and descriptions independent of layout',async()=>{
  const view=await northstarFixture(now); const factory=view.factory!; const rooms=factory.rooms;
  assert.equal(rooms.length,24); assert.equal(new Set(rooms.map(r=>r.id)).size,24);
  assert.deepEqual(rooms.map(({id,name})=>[id,name]),factoryCatalog.rooms);
  // Rendering is an ID lookup, not positional association. A reordered local
  // view still joins each catalog identity to its own name and explanation.
  const reordered=[...rooms].reverse();
  for(const [id,name] of factoryCatalog.rooms) {
    const row=reordered.find(r=>r.id===id)!;
    assert.equal(row.name,name); assert.ok(row.limitation.length>0);
  }
  const panel=source('./NorthstarPanels.tsx');
  assert.match(panel,/catalog\.map\(\(\[id, name\]\) => \{ const row = rows\?\.find\(r => r\.id === id\)/);
  assert.match(panel,/<h3>\{name\}<\/h3>/); assert.match(panel,/>Inspect \{name\}<\/button>/);
  assert.match(panel,/<p>\{row\?\.limitation \?\? 'NO_VERIFIED_PROJECTION'\}<\/p>/);
  assert.doesNotMatch(panel,/rows\??\.\[|rows\[|row\.name\.slice|substring|text-overflow/);
  assert.equal(validFactory(factory,view.session,view.source_generation,view.source_cycle,view.phase),true);
  for(const mutate of [
    (f:typeof factory)=>{f.rooms[1]=structuredClone(f.rooms[0])},
    (f:typeof factory)=>{f.rooms.pop()},
    (f:typeof factory)=>{f.rooms[0].name=f.rooms[1].name},
    (f:typeof factory)=>{f.rooms[0].id='unregistered_room'},
    (f:typeof factory)=>{[f.rooms[0].id,f.rooms[1].id]=[f.rooms[1].id,f.rooms[0].id]},
  ]) {
    const changed=structuredClone(view); mutate(changed.factory!);
    changed.factory!.content_hash=await contentHash(changed.factory! as unknown as Record<string,unknown>);
    assert.equal(validFactory(changed.factory,changed.session,changed.source_generation,changed.source_cycle,changed.phase),false);
    await assert.rejects(admitProjection(changed,null,now),/PROJECTION_CONTRACT_REJECTED/);
  }
  const outputs=northstarFloorOutputs({view,status:'CURRENT',reason:'VERIFIED'});
  assert.equal(AUCTION_ROOMS.length,18);assert.equal(new Set(AUCTION_ROOMS.map(r=>r.id)).size,18);
  assert.deepEqual(Object.keys(outputs).sort(),AUCTION_ROOMS.map(r=>r.id).sort());
  for(const station of AUCTION_ROOMS) { assert.ok(station.label.length>0); assert.ok(outputs[station.id].value.length>0); }
  const floor=source('./AuctionFactory.tsx');
  assert.match(floor,/output=\{outputs\[room\.id\]\}/);
  assert.match(floor,/data-room-id=\{room\.id\}/); assert.match(floor,/Open \$\{room\.label\}/);
  assert.match(floor,/<small>\{output\.value\}<\/small>/);
  const css=source('./NorthstarFullSession.css');
  assert.match(css,/\.auction-level \.auction-room:focus-visible \{ outline: 3px solid #edc88b; outline-offset: 3px/);
  assert.match(css,/\.auction-level \{ padding: .75rem/);
  assert.match(css,/\.auction-level__rooms[^}]+gap: 1rem; padding: .5rem/);
  // Only required explanation overflow is changed; decorative clipping and the
  // previously proven nested-text/neighbor-overlap detector remain intact.
  assert.doesNotMatch(css,/\.northstar-full-session\s*\*\s*\{[^}]*overflow/);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  for(const name of ['realClipping','decorative','longNestedName','realOverlap']) assert.ok(runner.includes('cases.'+name));
});
test('retained service-core scenery is bound below content in an isolated pointer-inert layer',()=>{
  const factory=source('./AuctionFactory.tsx');const floor=factory.split('export function NorthstarAuctionFactory(')[1].split('function Room(')[0];
  assert.match(floor,/<div className="northstar-service-decoration" aria-hidden="true"><div className="auction-service-core">/);
  assert.doesNotMatch(factory.split('export function NorthstarAuctionFactory(')[0],/northstar-service-decoration/);
  const css=source('./NorthstarFullSession.css');
  assert.match(css,/\.auction-building \{[^}]*isolation: isolate/);
  assert.match(css,/\.northstar-service-decoration \{ position: absolute; inset: 0; z-index: 0; pointer-events: none/);
  assert.match(css,/\.northstar-service-decoration \* \{ pointer-events: none/);
  assert.match(css,/\.auction-level \{[^}]*z-index: 1; isolation: isolate/);
  assert.doesNotMatch(css,/\.northstar-full-session\s*\*\s*\{[^}]*(?:z-index|overflow)/);
});
test('flow headings have no legacy parallax or constrained text height',()=>{
  const css=source('./NorthstarFullSession.css');
  assert.match(css,/\.auction-house-mark \{ position: static; transform: none !important; transition: none/);
  assert.doesNotMatch(css,/\.auction-house-mark[^{}]*\{[^}]*(?:max-height|line-clamp|text-overflow)/);
  assert.match(css,/\.northstar-full-session \{ min-width: 0; overflow-wrap: anywhere/);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  assert.match(runner,/DECORATION_ABOVE_CONTENT/);assert.match(runner,/DECORATION_INTERCEPTS_POINTER/);
  assert.match(runner,/data\['decoration'\]\['violations'\]/);
  assert.match(runner,/data\['clipped'\]/);assert.match(runner,/data\['textOverlaps'\]/);
});

const settlementScript=source('../../scripts/truth_spine_northstar_browser.py').split('SETTLEMENT_GEOMETRY = r"""')[1].split('"""')[0];
function settlementHarness() {
  let width=100,at=0,next=0;
  const frames=new Map<number,(at:number)=>void>(); const timers=new Map<number,()=>void>();
  let fontsReady!:()=>void;
  const fonts={status:'loading',ready:new Promise<void>(resolve=>{fontsReady=resolve})};
  const root={tagName:'MAIN',id:'fixture',className:'northstar-full-session',hidden:false,inert:false,parentElement:null,scrollLeft:0,scrollTop:0,querySelectorAll:()=>[],getBoundingClientRect:()=>({left:0,right:width,top:0,bottom:80,width,height:80})};
  const context={location:{href:'http://localhost/review/#gallery'},innerWidth:1512,innerHeight:825,devicePixelRatio:1,scrollX:0,scrollY:0,NodeFilter:{SHOW_TEXT:4},getComputedStyle:()=>({display:'block',visibility:'visible',transform:'none'}),
    document:{querySelector:(selector:string)=>selector.includes('nav')?{textContent:'Gallery'}:root,getElementById:()=>({}),fonts,getAnimations:()=>[],createTreeWalker:()=>({nextNode:()=>null}),documentElement:{scrollWidth:1512,clientWidth:1512},scrollingElement:{scrollLeft:0,scrollTop:0}},
    requestAnimationFrame:(fn:(at:number)=>void)=>{frames.set(++next,fn);return next},cancelAnimationFrame:(id:number)=>frames.delete(id),
    setTimeout:(fn:()=>void)=>{timers.set(++next,fn);return next},clearTimeout:(id:number)=>timers.delete(id)};
  const api=runInNewContext(settlementScript+'\n({settleNorthstar,geometryFrame,stableGeometryPair,visibleRequiredElement})',context);
  return {api,root,context,frames,fonts,load:()=>{fonts.status='loaded';fontsReady()},width:(value:number)=>{width=value},step:()=>{const pending=[...frames.values()];frames.clear();for(const fn of pending)fn(++at)},timeout:()=>{for(const fn of [...timers.values()])fn()}};
}
const flushFonts=async()=>{for(let i=0;i<5;i++)await Promise.resolve()};
test('C6 settlement waits for fonts and two consecutive equal animation-frame pairs',async()=>{
  const h=settlementHarness();const pending=h.api.settleNorthstar();await flushFonts();assert.equal(h.frames.size,0);
  h.load();await flushFonts();h.step();h.step();assert.equal(h.frames.size,1);h.step();
  const result=await pending;assert.equal(result.ok,true);assert.equal(result.samples.length,3);assert.equal(result.consecutiveMatches,2);
  assert.equal(result.coordinateSpace,'viewport-css-px');assert.equal(result.fonts,'loaded');
});
test('C6 delayed layout and current nested-scroll coordinates reset the stability run',async()=>{
  const h=settlementHarness();h.load();const pending=h.api.settleNorthstar();await flushFonts();h.step();h.width(120);h.root.scrollTop=96;h.step();h.step();assert.equal(h.frames.size,1);h.root.scrollTop=0;h.step();h.step();h.step();
  const r=await pending;assert.equal(r.ok,true);assert.equal(r.samples.length,6);assert.equal(r.samples[1].elements[0][5],96);assert.equal(r.samples[5].elements[0][5],0);
});
test('C6 requested post-scroll position must be reached, not merely stable elsewhere',async()=>{
  const h=settlementHarness();h.load();h.context.scrollY=100;h.context.document.scrollingElement.scrollTop=100;
  const p=h.api.settleNorthstar({scrollTarget:[0,0]});await flushFonts();h.step();h.step();h.step();assert.equal(h.frames.size,1);
  h.context.scrollY=0;h.context.document.scrollingElement.scrollTop=0;h.step();h.step();h.step();const r=await p;
  assert.equal(r.ok,true);assert.deepEqual(Array.from(r.samples.at(-1).scroll),[0,0,0,0]);
});
test('C6 missing fonts, wrong destination and changing geometry time out with evidence',async()=>{
  for(const mode of ['fonts','destination','geometry']) {
    const h=settlementHarness();if(mode!=='fonts')h.load();const p=h.api.settleNorthstar({destination:mode==='destination'?'Cases':'Gallery'});await flushFonts();
    for(let i=0;i<4;i++){if(mode==='geometry')h.width(100+i);h.step()}
    h.timeout();const r=await p;assert.equal(r.ok,false);assert.equal(r.reason,'LAYOUT_SETTLEMENT_TIMEOUT');
    assert.equal(r.samples.length,mode==='fonts'?0:4);assert.equal(h.frames.size,0);
  }
});
test('C6 coordinate-space mismatches fail rather than shifting boxes or widening tolerance',()=>{
  const geometry=source('../../scripts/truth_spine_northstar_browser.py').split('TEXT_GEOMETRY = r"""')[1].split('"""')[0];
  const {outside,viewportBox}=runInNewContext(geometry+'\n({outside,viewportBox})');
  const box=viewportBox({left:0,right:100,top:0,bottom:100,width:100,height:100});
  assert.throws(()=>outside({...box,space:'document-css-px'},box,true,true),/COORDINATE_SPACE_MISMATCH/);
  assert.equal(outside({...box,top:-10},box,true,true),true);assert.equal(outside(box,box,true,true),false);
  const h=settlementHarness();const frame=h.api.geometryFrame(h.root);
  assert.throws(()=>h.api.stableGeometryPair({...frame,fonts:'loaded'}, {...frame,fonts:'loaded',coordinateSpace:'document-css-px'}),/COORDINATE_SPACE_MISMATCH/);
});
test('C6 hidden destinations are excluded until activation, without named-element suppression',()=>{
  const h=settlementHarness();assert.equal(h.api.visibleRequiredElement(h.root),true);
  h.root.hidden=true;assert.equal(h.api.visibleRequiredElement(h.root),false);h.root.hidden=false;assert.equal(h.api.visibleRequiredElement(h.root),true);
  h.root.inert=true;assert.equal(h.api.visibleRequiredElement(h.root),false);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  assert.match(runner,/settle\('navigation:'\+label,destination=label\)/);assert.match(runner,/settle\('capture:'\+name\)/);
  assert.match(runner,/SCREENSHOT_GEOMETRY_CHANGED/);assert.match(runner,/realClipping/);assert.match(runner,/realOverlap/);
});
test('C6 repeated settled samples are deterministic and factory focus cannot scroll away its heading',async()=>{
  const signatures=[];
  for(let i=0;i<2;i++){const h=settlementHarness();h.load();const p=h.api.settleNorthstar();await flushFonts();h.step();h.step();h.step();signatures.push((await p).samples.at(-1).signature)}
  assert.equal(signatures[0],signatures[1]);
  const css=source('./NorthstarFullSession.css');assert.match(css,/\.northstar-full-session \.auction-factory \{[^}]*overflow: clip/);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');assert.match(runner,/FACTORY_HIDDEN_SCROLL_REGRESSION/);
  assert.match(runner,/\['hidden','clip'\]/);assert.doesNotMatch(runner,/geometry\.clipped\.filter/);
});

test('C7 spine belongs to the explicit Northstar underlay, leaving permanent markup unchanged',()=>{
  const factory=source('./AuctionFactory.tsx');const [permanent,northstar]=factory.split('export function NorthstarAuctionFactory(');
  assert.match(permanent,/<div className="auction-evidence-spine" aria-hidden="true">/);
  assert.match(northstar,/<div className="northstar-service-decoration" aria-hidden="true"><div className="auction-service-core">[\s\S]*?<div className="auction-evidence-spine">/);
  assert.equal(northstar.match(/className="auction-evidence-spine"/g)?.length,1);
  const scene=northstar.split('{levels.map')[0];assert.ok(scene.includes('className="auction-evidence-spine"'));
  const css=source('./NorthstarFullSession.css');
  assert.match(css,/\.northstar-service-decoration \.auction-evidence-spine \{ z-index: auto; \}/);
  assert.match(css,/\.northstar-service-decoration \* \{ pointer-events: none/);
  assert.match(css,/:focus-visible.*outline: 3px/);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  for(const gate of ['EVIDENCE_SPINE_ESCAPED_LAYER','DECORATION_ABOVE_CONTENT','DECORATION_INTERCEPTS_POINTER','cases.escapedSpine','cases.boundSpine'])assert.ok(runner.includes(gate));
});
test('C7 fixture clock is isolated from unchanged live polling and expiration contracts',async()=>{
  const live=source('./northstarSession.ts');
  assert.match(live,/clock: \(\) => number = Date.now/);
  assert.match(live,/setTimeout\(poll, 5000\)/);assert.match(live,/> 15_000/);
  assert.doesNotMatch(live,/FixtureDate|__northstarFixture|fixture-clock/);
  for(const file of ['./NorthstarFullSession.tsx','./NorthstarSessionContext.tsx'])assert.doesNotMatch(source(file),/FixtureDate|__northstarFixture|fixture-clock/);
  const view=await northstarFixture(now);const admitted=await admitProjection(view,null,now);
  assert.equal(ageProjection({view:admitted,status:'CURRENT',reason:'test'},now+16000).status,'STALE');
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  assert.match(runner,/location.origin!=='http:\/\/127.0.0.1:5291'/);
  assert.match(runner,/packaged_html_sha256/);assert.match(runner,/fixture_wrapper_html_sha256/);
  assert.match(runner,/window.__northstarFixture.clock.offset=16000/);
});
test('C7 capture reads committed context and visible identities, not manufactured DOM hashes',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  const identity=runner.split('CAPTURE_IDENTITY = r"""')[1].split('"""')[0];
  assert.match(identity,/fiber.memoizedProps\?\.value/);
  assert.match(identity,/fields\['Source generation'\]!==v.source_generation/);
  assert.match(identity,/v.factory\?\.content_hash!==expected.projection_content_hash/);
  assert.doesNotMatch(identity,/setAttribute|memoizedProps\s*=|textContent\s*=/);
  assert.match(runner,/data\['beforeIdentity'\]=js\(CAPTURE_IDENTITY/);
  assert.match(runner,/data\['afterIdentity'\]=js\(CAPTURE_IDENTITY/);
  assert.match(runner,/rejected_captures/);
});

import { activateNorthstarDialog } from './dialogAccessibility.ts';
const obstructionScript=source('../../scripts/truth_spine_northstar_browser.py').split('OBSTRUCTION_GEOMETRY = r"""')[1].split('"""')[0];
test('C8 paint order compares local stacking contexts, not unrelated z-index numbers',()=>{
  const {paintRelation}=runInNewContext(obstructionScript+'\n({paintRelation})');
  const root={key:'building',z:0,order:0};
  const scenery=[root,{key:'scene',z:0,order:1},{key:'route',z:21,order:4}];
  const control=[root,{key:'floor',z:1,order:2},{key:'room',z:0,order:3}];
  assert.equal(paintRelation(scenery,control),'BELOW');
  assert.equal(paintRelation([root,{key:'escaped-route',z:21,order:4}],control),'ABOVE');
  assert.equal(paintRelation(control,control),'SAME_CONTEXT_UNPROVEN');
  assert.equal(paintRelation([root,{key:'before',z:-1,order:-1}],[root]),'BELOW');
  assert.equal(paintRelation([root,{key:'a',z:1,order:1}],[root,{key:'b',z:1,order:2}]),'BELOW');
});
test('C8 route and foundation are bounded by the explicit decorative layer before all floors',()=>{
  const northstar=source('./AuctionFactory.tsx').split('export function NorthstarAuctionFactory(')[1].split('function Room(')[0];
  const beforeFloors=northstar.split('{levels.map')[0];
  const scene=beforeFloors.split('className="northstar-service-decoration" aria-hidden="true">')[1];
  for(const name of ['auction-route','auction-foundation','auction-roofline','auction-service-core','auction-evidence-spine']){
    assert.ok(scene.includes(name));assert.equal(northstar.split(name).length,2);
  }
  const css=source('./NorthstarFullSession.css');
  assert.match(css,/\.northstar-service-decoration \{[^}]*z-index: 0/);
  assert.match(css,/\.auction-level \{[^}]*z-index: 1; isolation: isolate/);
  assert.match(css,/\.northstar-service-decoration \{[^}]*overflow: clip/);
  assert.match(css,/\.northstar-full-session \[aria-hidden="true"\][\s\S]*?\*::after \{ pointer-events: none/);
  assert.doesNotMatch(css,/z-index:\s*(?:999|9999)/);
});
test('C8 obstruction detector checks generated paint, text, controls, focus and active destinations',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  for(const value of ["['::before','::after']","kind:'text'","kind:'control'","kind:'focus'","document.elementFromPoint","SAME_CONTEXT_UNPROVEN","RESOLVED_ABSOLUTE_PSEUDO","DECORATION_POINTER_EVENTS_ENABLED","hiddenInactive","OWN_BACKGROUND_NOT_A_FOREGROUND_LAYER"])assert.ok(obstructionScript.includes(value));
  for(const gate of ['cases.realText','cases.realControl','cases.realFocus','cases.pointer','cases.harmless','cases.pseudo','cases.hidden','cases.activation','OBSTRUCTION_DETECTOR_REGRESSION_FAILED'])assert.ok(runner.includes(gate));
  assert.match(runner,/or census\['violations'\]/);
  assert.match(runner,/\['policy','monitoring','learning','judgment'\]/);
  assert.match(runner,/native_click_escape_exact_focus/);
  assert.match(runner,/for width in \[1512,1020,386\]/);
  assert.match(runner,/click\(name\); time.sleep\(.15\); capture/);
  assert.match(runner,/beforeIdentity.*CAPTURE_IDENTITY/);
});

function modalHarness() {
  const listeners=new Map<string,Set<(e:unknown)=>void>>();
  const inline=()=>{const values=new Map<string,[string,string]>();return {getPropertyValue:(p:string)=>values.get(p)?.[0]||'',getPropertyPriority:(p:string)=>values.get(p)?.[1]||'',setProperty:(p:string,v:string,priority='')=>values.set(p,[v,priority]),removeProperty:(p:string)=>values.delete(p)}};
  const restore:unknown[]=[];
  const doc={activeElement:null as unknown,body:{style:inline()},documentElement:{style:inline()},defaultView:{scrollX:7,scrollY:419,scrollTo:(v:unknown)=>restore.push(v),getComputedStyle:()=>({display:'block',visibility:'visible'})},
    addEventListener:(type:string,fn:(e:unknown)=>void)=>{if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type)!.add(fn)},
    removeEventListener:(type:string,fn:(e:unknown)=>void)=>listeners.get(type)?.delete(fn)};
  const element=(tag='BUTTON',parent:unknown=null)=>{
    const attrs=new Map<string,string>();
    const events=new Map<string,Set<()=>void>>();
    const e={tagName:tag,parentElement:parent,tabIndex:0,inert:false,visible:true,style:inline(),open:true,
      addEventListener:(type:string,fn:()=>void)=>{if(!events.has(type))events.set(type,new Set());events.get(type)!.add(fn)},
      removeEventListener:(type:string,fn:()=>void)=>events.get(type)?.delete(fn),
      emit:(type:string)=>{for(const fn of [...events.get(type)||[]])fn()},eventCount:()=>[...events.values()].reduce((n,v)=>n+v.size,0),
      getAttribute:(n:string)=>attrs.get(n)??null,setAttribute:(n:string,v:string)=>attrs.set(n,v),removeAttribute:(n:string)=>attrs.delete(n),
      closest:()=>e.inert||attrs.get('aria-hidden')==='true'?e:null,
      contains:(x:unknown)=>x===e||(x as {parentElement?:unknown})?.parentElement===e,
      getClientRects:()=>e.visible?[{}]:[],querySelectorAll:()=>[] as unknown[],querySelector:()=>null,
      focus:()=>{doc.activeElement=e;for(const f of listeners.get('focusin')||[])f({target:e})}};
    return e;
  };
  const modal=element('DIV'),heading=element('H2',modal),close=element('BUTTON',modal),summary=element('SUMMARY',modal),opener=element(),background=element('MAIN');
  heading.tabIndex=-1;modal.querySelectorAll=()=>[close,summary];
  const key=(name:string,shift=false,repeat=false)=>{const event={key:name,shiftKey:shift,repeat,isComposing:false,defaultPrevented:false,stopped:false,preventDefault(){this.defaultPrevented=true},stopImmediatePropagation(){this.stopped=true}};for(const fn of [...listeners.get('keydown')||[]]){fn(event);if(event.stopped)break}return event};
  let closes=0;
  const activate=(override={})=>activateNorthstarDialog({dialog:modal,initialFocus:heading,opener,background:[background],close:()=>{closes++},documentTarget:doc,...override} as unknown as Parameters<typeof activateNorthstarDialog>[0]);
  return {doc,listeners,restore,element,modal,heading,close,summary,opener,background,key,activate,closes:()=>closes};
}
test('C9 owned scroll lock preserves prior styles and restores exact scroll/focus once',()=>{
  const h=modalHarness();h.doc.body.style.setProperty('position','relative','important');h.background.setAttribute('aria-hidden','false');
  const stop=h.activate();assert.equal(h.doc.body.style.getPropertyValue('position'),'fixed');assert.equal(h.doc.body.style.getPropertyValue('top'),'-419px');assert.equal(h.doc.documentElement.style.getPropertyValue('overflow'),'hidden');
  assert.equal(h.doc.activeElement,h.heading);assert.equal(h.background.inert,true);
  stop();stop();assert.equal(h.doc.body.style.getPropertyValue('position'),'relative');assert.equal(h.doc.body.style.getPropertyPriority('position'),'important');
  assert.equal(h.background.inert,false);assert.equal(h.background.getAttribute('aria-hidden'),'false');assert.equal(h.doc.activeElement,h.opener);
  assert.deepEqual(h.restore,[{left:7,top:419,behavior:'instant'}]);assert.equal(h.listeners.get('keydown')?.size,0);assert.equal(h.listeners.get('focusin')?.size,0);
});
test('C9 Tab and Shift+Tab wrap visible controls including disclosure summaries',()=>{
  const h=modalHarness(),stop=h.activate();h.key('Tab');assert.equal(h.doc.activeElement,h.close);
  h.key('Tab',true);assert.equal(h.doc.activeElement,h.summary);h.key('Tab');assert.equal(h.doc.activeElement,h.close);
  h.summary.visible=false;h.key('Tab',true);assert.equal(h.doc.activeElement,h.close);
  h.close.visible=false;h.key('Tab');assert.equal(h.doc.activeElement,h.heading);
  h.opener.focus();assert.equal(h.doc.activeElement,h.heading);stop();
});
test('C9 Escape is idempotent and only the topmost owned modal closes',()=>{
  const h=modalHarness(),stop=h.activate();
  const inner=h.element('DIV'),heading=h.element('H2',inner);heading.tabIndex=-1;
  let closed=0;const stopInner=h.activate({dialog:inner,initialFocus:heading,opener:h.close,background:[],close:()=>{closed++}});
  h.key('Escape',false,true);assert.equal(closed,0);h.key('Escape');h.key('Escape');assert.equal(closed,1);assert.equal(h.closes(),0);
  stopInner();assert.equal(h.doc.body.style.getPropertyValue('position'),'fixed');assert.equal(h.doc.activeElement,h.close);
  h.key('Escape');assert.equal(h.closes(),1);stop();assert.equal(h.restore.length,1);
});
test('C9 repeated open and close restores listeners, inert state and scroll ownership',()=>{
  const h=modalHarness();for(let i=0;i<12;i++){const stop=h.activate();assert.equal(h.listeners.get('keydown')?.size,1);h.key('Escape');stop();assert.equal(h.listeners.get('keydown')?.size,0);assert.equal(h.background.inert,false)}
  assert.equal(h.closes(),12);assert.equal(h.restore.length,12);
});
test('C9 modal geometry rejects offscreen close controls, clipping and background scrolling',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py'),text=runner.split('TEXT_GEOMETRY = r"""')[1].split('"""')[0],geometry=runner.split('DIALOG_GEOMETRY = r"""')[1].split('"""')[0];
  const {dialogFailures}=runInNewContext(text+geometry+'\n({dialogFailures})');
  const rect={space:'viewport-css-px',left:12,right:374,top:12,bottom:813,width:362,height:801};
  const box={rect,scroll:[0,0,362,1700,362,601]};const d={viewport:[386,825],surface:box,header:box,body:box,close:box,closeHit:true,role:'dialog',ariaModal:'true',name:'Monitoring Floor',active:{contained:true},document:{bodyPosition:'fixed',htmlOverflow:'hidden'},required:{clipped:[],overlaps:[]}};
  assert.equal(dialogFailures(d).length,0);
  assert.ok(dialogFailures({...d,close:{...box,rect:{...rect,right:397}}}).includes('close_OUTSIDE_VIEWPORT'));
  assert.ok(dialogFailures({...d,required:{clipped:[{}],overlaps:[]}}).includes('REQUIRED_TEXT_CLIPPED'));
  assert.ok(dialogFailures({...d,document:{bodyPosition:'static',htmlOverflow:'visible'}}).includes('BACKGROUND_NOT_LOCKED'));
  assert.ok(dialogFailures({...d,body:{...box,scroll:[0,0,401,1700,362,601]}}).includes('HORIZONTAL_DIALOG_OVERFLOW'));
});
test('C9 all stable stations use one bounded scroller and fixed heading/close area',()=>{
  assert.equal(AUCTION_ROOMS.length,18);assert.equal(new Set(AUCTION_ROOMS.map(r=>r.id)).size,18);
  const component=source('./AuctionFactory.tsx').split('export function NorthstarRoomView(')[1];
  assert.equal(component.match(/className="northstar-dialog-body"/g)?.length,1);
  assert.match(component,/activateNorthstarDialog/);assert.match(component,/bodyRef.current\?\.scrollTo\(\{ top: 0/);
  assert.match(component,/aria-labelledby=\{titleId\}/);assert.match(component,/aria-label=\{`Close \$\{room.label\}`\}/);
  const css=source('./NorthstarFullSession.css');
  for(const side of ['top','right','bottom','left'])assert.ok(css.includes('env(safe-area-inset-'+side+')'));
  assert.match(css,/width: min\(1200px, 100%\)/);assert.match(css,/max-height: 100%/);assert.match(css,/\.northstar-dialog-body \{[\s\S]*?min-height: 0[\s\S]*?overflow: auto/);
  assert.match(css,/\.northstar-dialog-header \.auction-close \{\s*position: static/);
  assert.doesNotMatch(component,/text-overflow|ellipsis|\.slice\(/);
});

const dialogScript=source('../../scripts/truth_spine_northstar_browser.py').split('DIALOG_GEOMETRY = r"""')[1].split('"""')[0];
test('F3 dialog keeps a visible dimensioned scrollbar without weakening capture equality',()=>{
  const css=source('./NorthstarFullSession.css');
  assert.match(css,/overflow: auto; overflow-y: scroll/);
  assert.match(css,/\.northstar-full-session \.northstar-dialog-body::-webkit-scrollbar \{ width: 16px; height: 16px; \}/);
  assert.match(css,/\.northstar-dialog-body::-webkit-scrollbar-thumb \{\s*background: #b58242/);
  assert.doesNotMatch(css,/scrollbar-width:\s*none/);
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  assert.ok(runner.includes("'screenshotGeometryMatches':before['frame']==after['frame']"));
  assert.ok(runner.includes("receipt['screenshotGeometryMatches'] &= before['active']==after['active']"));
});
test('F2 multi-cast dialog reserves full content height for portraits, names and quiet evidence',()=>{
  const css=source('./NorthstarFullSession.css'),root=postcss.parse(css);
  const declarations=(selector:string)=>{const values:Record<string,string>={};root.walkRules(rule=>{if(rule.selector===selector)rule.walkDecls(d=>{values[d.prop]=d.value;});});return values;};
  const prefix='.northstar-full-session .northstar-dialog-body';
  assert.equal(declarations(prefix)['grid-auto-rows'],'max-content');
  const stage=prefix+' .auction-room-stage.is-multi-cast';
  assert.equal(declarations(stage).display,'grid');assert.equal(declarations(stage)['overflow'],'visible');
  assert.equal(declarations(stage+' .auction-room-cinema')['min-height'],'min-content');
  assert.equal(declarations(stage+' .auction-room-cinema article')['aspect-ratio'],'auto');
  assert.equal(declarations(stage+' .auction-room-cinema article').overflow,'visible');
  assert.equal(declarations(stage+' .auction-evidence-stage')['grid-row'],'auto');
  const macro=AUCTION_ROOMS.find(r=>r.id==='macro')!;assert.equal(macro.characterKeys.length,3);
  // The observed zero-height cinema and caption boxes must still fail admission.
  const text=source('../../scripts/truth_spine_northstar_browser.py').split('TEXT_GEOMETRY = r"""')[1].split('"""')[0];
  const {dialogFailures}=runInNewContext(text+dialogScript+'\n({dialogFailures})');
  const box={rect:{space:'viewport-css-px',left:12,right:1500,top:12,bottom:813},scroll:[0,0,1488,1600,1488,650]};
  assert.ok(dialogFailures({viewport:[1512,825],surface:box,header:box,body:box,close:box,closeHit:true,role:'dialog',ariaModal:'true',name:'Macro Desk',active:{contained:true},document:{bodyPosition:'fixed',htmlOverflow:'hidden'},required:{clipped:[{text:'Benny Basis Points',clips:[{rect:{height:0,top:233.9375,bottom:233.9375}}]}],overlaps:[]}}).includes('REQUIRED_TEXT_CLIPPED'));
});
test('C10 one, two and multiline heading ranges are distinct; genuine 19px overlap fails',()=>{
  const {headingLineOverlaps}=runInNewContext(dialogScript+'\n({headingLineOverlaps})');
  for(const count of [1,2,5]){
    const lines=Array.from({length:count},(_,i)=>({left:0,right:200,top:i*50,bottom:i*50+42}));
    assert.equal(headingLineOverlaps(lines).length,0);
  }
  assert.equal(headingLineOverlaps([{left:197,right:1160,top:483.703125,bottom:581.703125},{left:197,right:1010,top:562.703125,bottom:660.703125}]).length,1);
  // Even a same-text-node wrapped line must fail; requiredText's cross-node
  // checks alone cannot detect this. No broad overlap tolerance is introduced.
  assert.equal(headingLineOverlaps([{left:0,right:50,top:0,bottom:42},{left:0,right:50,top:41.9,bottom:84}]).length,1);
});
test('C10 typography remains scoped, content-height driven and naturally wrapping at every width',()=>{
  const css=source('./NorthstarFullSession.css'),body=css.split('.northstar-dialog-body :is(h2, h3, h4) {')[1].split('}')[0];
  for(const value of ['Georgia, serif','clamp(22px, 2.5vw, 36px)','line-height: 1.4','height: auto','max-height: none','max-width: 100%','margin: 0 0 1rem','white-space: normal','overflow-wrap: anywhere','overflow: visible'])assert.ok(body.includes(value));
  assert.doesNotMatch(body,/ellipsis|line-clamp|position: absolute|transform:|margin: -/);
  assert.match(css,/\.northstar-full-session \.northstar-station-dialog :focus \{\s*outline: 3px solid #edc88b; outline-offset: 3px/);
  assert.match(css,/scroll-margin-block: 12px/);assert.match(css,/scroll-padding-block: 1rem/);
  assert.match(source('./LivingWallApp.tsx'),/Governed shadow station evidence · \{status\}/);
});
test('C10 focus visibility fails closed for missing, clipped, covered or low-contrast rings',()=>{
  const {focusFailures}=runInNewContext(dialogScript+'\n({focusFailures})');
  const good={active:true,visible:true,name:'Original evidence identities and timestamps',outlineStyle:'solid',outlineWidth:3,opacity:1,clips:[],covered:[],contrast:8};
  assert.equal(focusFailures(good).length,0);
  for(const [change,reason] of [
    [{outlineStyle:'none'},'FOCUS_INDICATOR_MISSING'],[{outlineWidth:0},'FOCUS_INDICATOR_MISSING'],
    [{visible:false},'FOCUS_NOT_VISIBLE'],[{clips:['scrollport']},'FOCUS_INDICATOR_CLIPPED'],
    [{covered:['FIXED_HEADER']},'FOCUS_INDICATOR_COVERED'],[{covered:['decoration']},'FOCUS_INDICATOR_COVERED'],
    [{contrast:null},'FOCUS_CONTRAST_UNPROVEN'],[{contrast:2.99},'FOCUS_CONTRAST_UNPROVEN'],
  ] as const)assert.ok(focusFailures({...good,...change}).includes(reason));
});
test('C10 full owned Tab and Shift+Tab cycles include controls Safari can otherwise skip',()=>{
  const h=modalHarness(),body=h.element('DIV',h.modal),stop=h.activate();h.modal.querySelectorAll=()=>[h.close,body,h.summary];
  for(const expected of [h.close,body,h.summary,h.close]){assert.equal(h.key('Tab').defaultPrevented,true);assert.equal(h.doc.activeElement,expected)}
  for(const expected of [h.summary,body,h.close]){assert.equal(h.key('Tab',true).defaultPrevented,true);assert.equal(h.doc.activeElement,expected)}
  h.key('Escape');stop();assert.equal(h.doc.activeElement,h.opener);assert.deepEqual(h.restore,[{left:7,top:419,behavior:'instant'}]);
});
test('C10 browser measures typography, full focus cycles, scroller/header/decorations and bound screenshots',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  for(const value of ['headingTypography(surface)','headingLineOverlaps(lines)','HEADING_LINE_OVERLAP','focusMeasurement','backgroundSamples','outlineOffset','elementFromPoint','FIXED_HEADER','FOCUS_INDICATOR_CLIPPED','FOCUS_INDICATOR_COVERED','FOCUS_CONTRAST_UNPROVEN','collapsedTab','collapsedShiftTab','expandedTab','expandedShiftTab','DIALOG_LOGICAL_FOCUS_ORDER_FAILED','FOCUS_CAPTURE_GENERATION_CHANGED'])assert.ok(runner.includes(value));
  assert.match(runner,/\.\.\.dialogFailures\(d\),\.\.\.focus.failures/);
  assert.match(runner,/for width in \[1512,1020,386\]/);
  assert.match(runner,/native_click_escape_exact_focus/);
});

test('C11 station native buttons have explicit tab eligibility without changing the legacy renderer',()=>{
  const component=source('./AuctionFactory.tsx'),room=component.split('function NorthstarRoom(')[1].split('export function RoomView')[0];
  assert.match(room,/<button type="button" tabIndex=\{0\}/);
  assert.match(room,/data-room-id=\{room.id\}/);assert.match(room,/aria-label=\{`Open \$\{room.label\};/);
  assert.doesNotMatch(room,/onKeyDown|\.focus\(/);
  assert.match(room,/matches\(':focus-visible'\).*hasAttribute\('data-northstar-restored-focus'\)/);
  assert.match(room,/scrollIntoView\(\{ block: 'center', inline: 'nearest', behavior: 'instant' \}\)/);
  const legacy=component.split('function Room(')[1].split('function NorthstarRoom(')[0];assert.doesNotMatch(legacy,/tabIndex=\{0\}/);
  const factory=component.split('export function NorthstarAuctionFactory(')[1].split('function Room(')[0];
  assert.match(factory,/<NorthstarRoom key=\{room.id\}/);assert.equal(AUCTION_ROOMS.length,18);
});
test('C11 native Tab proof rejects setup focus, pointer, Option+Tab and untrusted or prevented events',()=>{
  const {nativeCardTabProof}=runInNewContext(dialogScript+'\n({nativeCardTabProof})');
  const key={type:'keydown',key:'Tab',trusted:true,shift:false,alt:false,prevented:false},focus={type:'focusin',trusted:true,target:'research'};
  assert.equal(nativeCardTabProof([key,focus],'research',false),true);
  assert.equal(nativeCardTabProof([{...key,shift:true},focus],'research',true),true);
  for(const events of [[focus],[{...key,key:'Enter'},focus],[{type:'pointerdown',trusted:true},focus],[{...key,alt:true},focus],[{...key,trusted:false},focus],[{...key,prevented:true},focus],[focus,key]])assert.equal(nativeCardTabProof(events,'research',false),false);
  assert.equal(nativeCardTabProof([key,focus],'radar',false),false);assert.equal(nativeCardTabProof([key,focus],'research',true),false);
});
test('C11 station indicator has an opaque contrast backing and restored focus is narrowly scoped',()=>{
  const css=source('./NorthstarFullSession.css'),block=css.split('.auction-room[data-northstar-restored-focus]:focus {')[1].split('}')[0];
  for(const x of ['outline: 3px solid #edc88b','outline-offset: 3px','0 0 0 8px #100c08','opacity: 1','filter: none'])assert.ok(block.includes(x));
  assert.match(css,/\.northstar-full-session \.auction-level \.auction-room:focus-visible,/);
  assert.match(dialogScript,/Number\(backing\[2\]\)>=pad\+1/);
  assert.match(dialogScript,/s.filter==='none'&&Number\(s.opacity\)===1/);
  assert.match(dialogScript,/contrast<3/);
});
test('C11 exact opener restoration marks only interactive stations and clears on pointer or blur',()=>{
  const h=modalHarness();h.opener.setAttribute('data-room-id','research');
  for(const event of ['pointerdown','blur']){
    const stop=h.activate();h.key('Escape');stop();stop();
    assert.equal(h.doc.activeElement,h.opener);assert.equal(h.opener.getAttribute('data-northstar-restored-focus'),'');assert.equal(h.opener.eventCount(),2);
    h.opener.emit(event);assert.equal(h.opener.getAttribute('data-northstar-restored-focus'),null);assert.equal(h.opener.eventCount(),0);
  }
  assert.equal(h.restore.length,2);
});
test('C11 browser audit uses actual forward/reverse traversal and separate diagnostic classifications',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py'),gallery=runner.split('    def gallery_audit(width):')[1].split('    def capture(')[0];
  assert.doesNotMatch(gallery,/\.focus\(/);
  for(const x of ['native_station_tab(width)','native_station_tab(width,True)','NATIVE_STATION_FORWARD_ORDER_FAILED','NATIVE_STATION_REVERSE_ORDER_FAILED','station_dialog_audit'])assert.ok(gallery.includes(x));
  assert.match(runner,/native_key\('\\ue007'\)/);assert.match(runner,/native_key\(' '\)/);
  assert.match(runner,/classification='DIAGNOSTIC_ONLY' if any\(\[args.diagnose_gallery/);
  assert.match(runner,/args.diagnose_modality,args.diagnose_keyboard_boundary/);
  assert.match(runner,/RESTORED_OPENER_NOT_VISIBLE/);
});

function componentBoundaryErrors(text: string): string[] {
  const file = ts.createSourceFile('AuctionFactory.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const errors = (file as unknown as {parseDiagnostics: unknown[]}).parseDiagnostics.map(() => 'PARSE_ERROR');
  const names = new Set<string>();
  for (const node of file.statements) if (ts.isFunctionDeclaration(node) && node.name) {
    if (names.has(node.name.text)) errors.push('DUPLICATE_COMPONENT');
    names.add(node.name.text);
  }
  for (const name of ['RoomView','NorthstarRoomView','NorthstarAuctionFactory']) {
    const node=file.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name);
    if (!node || !ts.canHaveModifiers(node) || !ts.getModifiers(node)?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword)) errors.push('MISSING_EXPORT:'+name);
  }
  return errors;
}
test('E parser rejects the exact duplicate/unclosed boundary and preserves module exports',()=>{
  const text=source('./AuctionFactory.tsx');assert.deepEqual(componentBoundaryErrors(text),[]);
  const broken=text.replace('export function RoomView(', 'export function RoomView() {\nexport function RoomView(');
  assert.ok(componentBoundaryErrors(broken).includes('PARSE_ERROR'));
  assert.ok(componentBoundaryErrors(broken).includes('MISSING_EXPORT:NorthstarRoomView'));
  assert.ok(componentBoundaryErrors(text.replace('export function NorthstarRoomView','function NorthstarRoomView')).length);
  assert.ok(componentBoundaryErrors(text+'\nfunction RoomView() {}').includes('DUPLICATE_COMPONENT'));
});
test('E bounded navigation never retries or falsely changes a refused route',()=>{
  let calls=0;const denied={pushState:()=>{calls++;throw new Error('SecurityError')}};
  assert.equal(boundedNavigation(denied,'#gallery','#cases',{}),false);assert.equal(calls,1);
  assert.equal(boundedNavigation(denied,'#gallery','#gallery',{}),true);assert.equal(calls,1);
  let target='';assert.equal(boundedNavigation({pushState:(_s,_t,u)=>{target=String(u)}},'#gallery','#cases',{}),true);assert.equal(target,'#cases');
});
test('E distinct restored identities resolve exact openers; duplicates and missing identities fail',()=>{
  const a={},b={},rows=[{id:'l7',element:a},{id:'l8',element:b}];
  for(const [id,expected] of [['l7',a],['l8',b],['l7',a],['l8',b]] as const)assert.equal(selectedOpener(id,[...rows].reverse()),expected);
  assert.equal(selectedOpener('missing',rows),null);assert.equal(selectedOpener('l7',[...rows,rows[0]]),null);
  assert.equal(selectedOpener(null,rows),null);
  const panel=source('./NorthstarPanels.tsx');assert.match(panel,/opener.current = resolveOpener\(id\)/);assert.doesNotMatch(panel,/opener.current \?\?=/);
});
test('E plaque uses the owned modal contract with polling-stable close callback and native semantics',()=>{
  const wall=source('./LivingWallApp.tsx');const isolated=wall.split('export function NorthstarLivingWall()')[1];
  assert.match(isolated,/const closePlaque = useCallback\(\(\) => setPlaque\(false\), \[\]\)/);
  assert.match(isolated,/NorthstarCollectorPlaque model=\{model\} opener=\{plaqueOpener\} close=\{closePlaque\}/);
  assert.doesNotMatch(isolated,/<CollectorPlaque|Resume Scene/);
  const plaque=isolated.split('function NorthstarCollectorPlaque(')[1];
  assert.match(plaque,/activateNorthstarDialog/);assert.match(plaque,/\}, \[close, opener\]\)/);
  assert.equal(plaque.match(/className="northstar-dialog-body"/g)?.length,1);
  assert.match(isolated,/<button disabled title="Isolated deny-only mode/);
  assert.match(plaque,/role="dialog" aria-modal="true"/);
});
test('E modified Tab is not intercepted by Northstar modal ownership',()=>{
  const text=source('./dialogAccessibility.ts').split('export function activateNorthstarDialog')[1];
  assert.match(text,/event.key !== 'Tab' \|\| event.ctrlKey \|\| event.metaKey \|\| event.altKey/);
  const {nativeCardTabProof}=runInNewContext(dialogScript+'\n({nativeCardTabProof})');
  const key={type:'keydown',key:'Tab',trusted:true,shift:false},focus={type:'focusin',trusted:true,target:'research'};
  for(const modifier of ['ctrl','meta','alt'])assert.equal(nativeCardTabProof([{...key,[modifier]:true},focus],'research',false),false);
  assert.equal(nativeCardTabProof([key,{type:'programmatic-focus'},focus],'research',false),false);
});
test('E alternative focus indicators require measured unfocused difference, geometry and contrast',()=>{
  const {focusFailures}=runInNewContext(dialogScript+'\n({focusFailures})');
  const f={active:true,visible:true,name:'Control',outlineStyle:'none',outlineWidth:0,opacity:1,clips:[],covered:[],contrast:null};
  for(const kind of ['box-shadow','border','background']) {
    const indicator={kind,changedFromUnfocused:true,width:3,contrast:5,geometryVerified:true};
    assert.equal(focusFailures({...f,alternativeIndicators:[indicator]}).length,0);
    for(const change of [{changedFromUnfocused:false},{width:1},{contrast:2.9},{geometryVerified:false}])assert.ok(focusFailures({...f,alternativeIndicators:[{...indicator,...change}]}).length);
    assert.ok(focusFailures({...f,clips:['viewport'],alternativeIndicators:[indicator]}).length);
    assert.ok(focusFailures({...f,covered:['decoration'],alternativeIndicators:[indicator]}).length);
  }
});
test('E source owns motion policy; screenshots use one admission boundary without CSS injection',()=>{
  const runner=source('../../scripts/truth_spine_northstar_browser.py');
  assert.doesNotMatch(settlementScript,/createElement\('style'\)|animation:none!important/);
  assert.match(source('./NorthstarFullSession.css'),/animation: none; transition: none/);
  for(const field of ['source_commit','build_input_hash','provenance_hash','output_hash','active_before','input_modality','screenshot_start','screenshotGeometryMatches'])assert.ok(runner.includes(field));
  assert.match(runner,/path.endswith\('\/screenshot'\)/);
});
test('E all nine immutable lifecycle fixtures remain deny-only and independently admitted',async()=>{
  for(const phase of sessionPhases){
    const view=await northstarFixture(now);view.phase=phase;view.factory!.phase=phase;
    for(const rows of [view.factory!.rooms,view.factory!.agents,view.factory!.governance,view.factory!.routes,view.factory!.history,view.factory!.subsystems,[view.factory!.day_trading]])for(const row of rows)row.phase=phase;
    view.factory!.content_hash=await contentHash(view.factory! as unknown as Record<string,unknown>);
    const admitted=await admitProjection(view,null,now);assert.equal(admitted.phase,phase);
    assert.ok(Object.values(admitted.capabilities).every(x=>x===false));assert.ok(Object.values(admitted.counters).every(x=>x===0));
    assert.equal(ageProjection({view:admitted,status:'CURRENT',reason:'FIXTURE'},now+15001).status,'STALE');
  }
  assert.equal(retainedFailure(emptyNorthstar).status,'UNAVAILABLE');
});
test('E source-driven three/two/one grids hold at every inherited breakpoint boundary',()=>{
  const root=postcss.parse(source('./NorthstarFullSession.css'));
  for(const width of [1512,1101,1100,1099,1020,851,850,849,701,700,699,521,520,519,401,400,399,386]){
    for(const target of ['.northstar-full-session .auction-level__rooms','.northstar-full-session .northstar-room-grid']){
      let columns='';root.walkRules(rule=>{if(!rule.selectors.includes(target))return;
        if(rule.parent?.type==='atrule'){const max=Number((rule.parent as postcss.AtRule).params.match(/max-width: (\d+)px/)?.[1]);if(!max||width>max)return;}
        rule.walkDecls('grid-template-columns',d=>{columns=d.value});
      });assert.equal(columns,width>1100?'repeat(3, minmax(0, 1fr))':width>700?'repeat(2, minmax(0, 1fr))':'minmax(0, 1fr)');
    }
  }
});
test('E polling does not require reactivation or tear down modal ownership',()=>{
  const h=modalHarness(),stop=h.activate();const initial=h.doc.activeElement;
  for(let i=0;i<20;i++){
    // Equivalent parent data changes do not call the stable effect cleanup.
    assert.equal(h.listeners.get('keydown')?.size,1);assert.equal(h.doc.activeElement,initial);
    assert.equal(h.doc.body.style.getPropertyValue('position'),'fixed');
  }
  stop();assert.equal(h.restore.length,1);assert.equal(h.doc.activeElement,h.opener);
  const factory=source('./AuctionFactory.tsx').split('export function NorthstarRoomView')[1];
  assert.match(factory,/\}, \[close, opener, roomId\]\)/);assert.doesNotMatch(factory,/\}, \[.*(?:model|governedContent)/);
});
