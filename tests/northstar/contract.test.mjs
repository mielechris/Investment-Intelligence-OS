import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fixtures, here, sha } from './prepare.mjs';
import config from './playwright.config.mjs';
import { surfaceFromViewport, decodeImages, portraitContract, portraitRasterComparison } from './capture-surface.mjs';
import bundle from './node_modules/playwright-core/lib/utilsBundle.js';
import {assertStructure,compareWebKit,limits} from './webkit-perceptual.mjs';
const contract = JSON.parse(readFileSync(resolve(here, '.build/contract.json')));

test('exact 54-case matrix per engine, all engines required', () => {
  assert.equal(contract.stations.length, 18);
  assert.equal(new Set(contract.stations.map(x=>x.id)).size, 18);
  assert.equal(contract.stations.length * 3, 54);
  assert.deepEqual(config.projects.map(x=>x.name), ['chromium','firefox','webkit']);
  assert.equal(config.retries, 0); assert.equal(config.forbidOnly, true);
  assert.equal(config.webServer.reuseExistingServer, false);
  assert(config.testIgnore.includes('**/artifacts/**'));
});
test('fixture independent reconstruction, all phases hash-bound and deny-only', async () => {
  assert.deepEqual(await fixtures(), contract.fixtures);
  for (const [phase, value] of Object.entries(contract.fixtures)) {
    assert.equal(sha(JSON.stringify(value)), contract.manifest.fixtureHashes[phase]);
    assert.equal(value.factory.rooms.length,24); assert.equal(value.factory.agents.length,8);
    assert.equal(value.factory.governance.length,3);
    assert(Object.values(value.capabilities).every(x=>x===false));
    assert(Object.values(value.counters).every(x=>x===0));
  }
});
test('shared geometry parses without Safari or other browser globals at import', () => {
  for(const name of ['TEXT_GEOMETRY','OBSTRUCTION_GEOMETRY','DIALOG_GEOMETRY','SETTLEMENT_GEOMETRY','DECORATION_GEOMETRY','CAPTURE_IDENTITY'])
    assert.doesNotThrow(()=>new Function(contract.geometry[name]));
});
test('manifest and fixture mutations change their hash', () => {
  assert.equal(sha(JSON.stringify(contract.manifest)),contract.manifestHash);
  const altered=structuredClone(contract.manifest);altered.authorities='ENABLED';
  assert.notEqual(sha(JSON.stringify(altered)),contract.manifestHash);
});
test('all 162 surface baselines are hash-bound, full viewport scope is retained', () => {
  const record=JSON.parse(readFileSync(resolve(here,'baseline-scope.json')));
  assert.equal(record.actualCapture,false);
  assert.equal(record.records.length,162);
  const names=new Set();
  for(const row of record.records){
    const name=row.engine+'/'+row.name;assert(!names.has(name));names.add(name);
    assert.equal(sha(readFileSync(resolve(here,'snapshots/darwin',name))),row.surface_sha256);
    assert.equal(row.rectangle.y,12);assert.equal(row.rectangle.height,801);
    assert.equal(row.rectangle.width,Math.min(1200,row.viewport[0]-24));
  }
  const spec=readFileSync(resolve(here,'northstar.spec.mjs'),'utf8');
  assert(spec.includes("'-full-viewport'"));
  assert(spec.includes("caret:'hide',scale:'css'"));
  assert(spec.includes('document.documentElement.scrollWidth-document.documentElement.clientWidth'));
  assert(spec.includes('else expect(surface).toMatchSnapshot'));
});
for(const name of ['1512-expansion','1020-control'])test(name+' raster exception cannot hide movement, clipping, text or color changes',()=>{
  const expected=readFileSync(resolve(here,'snapshots/darwin/webkit',name+'.png'));
  const image=bundle.PNG.sync.read(expected),r=portraitContract.cases[name].pixelRegion;
  const altered=edit=>{const a=bundle.PNG.sync.read(expected);edit(a);return bundle.PNG.sync.write(a)};
  assert(portraitRasterComparison(name,expected,expected).ok);
  const harmless=altered(a=>{const i=((r.y+5)*a.width+r.x+5)*4;a.data[i]=a.data[i]<255?a.data[i]+1:a.data[i]-1;});
  assert(portraitRasterComparison(name,expected,harmless).ok);
  assert(!portraitRasterComparison(name,expected,altered(a=>{a.data[(20*a.width+20)*4]^=1})).ok,'one outside text pixel must fail');
  for(const shift of [.5,1]){
   const moved=altered(a=>{for(let y=r.y;y<r.y+r.height;y++)for(let x=r.x+1;x<r.x+r.width;x++)for(let c=0;c<3;c++){const i=(y*a.width+x)*4+c;a.data[i]=Math.round(image.data[i]*(1-shift)+image.data[i-4]*shift)}});
   assert(!portraitRasterComparison(name,expected,moved).ok,'half/full pixel movement must fail');
  }
  const clipped=altered(a=>{for(let y=r.y;y<r.y+r.height;y++)for(let x=r.x;x<r.x+3;x++)for(let c=0;c<3;c++)a.data[(y*a.width+x)*4+c]=0});
  assert(!portraitRasterComparison(name,expected,clipped).ok,'clipping must fail');
  const recolored=altered(a=>{for(let y=r.y;y<r.y+r.height;y++)for(let x=r.x;x<r.x+r.width;x++)for(let c=0;c<3;c++){const i=(y*a.width+x)*4+c;a.data[i]=Math.min(255,a.data[i]+10)}});
  assert(!portraitRasterComparison(name,expected,recolored).ok,'meaningful color shift must fail');
  assert.throws(()=>portraitRasterComparison(name,harmless,expected),/BASELINE_BINDING/);
  assert.throws(()=>portraitRasterComparison('unreviewed',expected,expected),/UNREVIEWED/);
  assert.deepEqual(Object.keys(portraitContract.cases),['1512-expansion','1020-control']);
  assert.equal(portraitContract.outsideImageTolerance,0);
});
test('viewport surface extraction preserves every channel and rejects invalid geometry', () => {
  const input = new bundle.PNG({width:4,height:4});
  for(let i=0;i<input.data.length;i++)input.data[i]=i;
  const bytes=bundle.PNG.sync.write(input);
  const output=bundle.PNG.sync.read(surfaceFromViewport(bytes,{x:1,y:1,width:2,height:2}));
  for(let y=0;y<2;y++)for(let x=0;x<2;x++)
    assert.deepEqual(output.data.subarray((y*2+x)*4,(y*2+x+1)*4),input.data.subarray(((y+1)*4+x+1)*4,((y+1)*4+x+2)*4));
  assert.throws(()=>surfaceFromViewport(bytes,{x:0.5,y:0,width:2,height:2}),/INTEGER_SURFACE/);
  assert.throws(()=>surfaceFromViewport(bytes,{x:3,y:3,width:2,height:2}),/OUTSIDE_VIEWPORT/);
  assert.equal(config.expect.toMatchSnapshot.maxDiffPixels,0);
  assert.equal(config.expect.toMatchSnapshot.threshold,0);
});
test('image barrier waits for explicit decoding, rejects errors and never substitutes an image', async () => {
  let release;let done=false;
  const image={complete:false,naturalWidth:0,naturalHeight:0,currentSrc:'fixture-image',decode:()=>new Promise(resolve=>{release=resolve})};
  const pending=decodeImages([image]).then(value=>{done=true;return value});
  assert.equal(done,false);assert.equal(typeof release,'function');
  image.complete=true;image.naturalWidth=10;image.naturalHeight=20;release();
  assert.deepEqual(await pending,[{source:'fixture-image',width:10,height:20}]);
  await assert.rejects(decodeImages([{...image,decode:()=>Promise.reject(Error('DECODE_REJECTED'))}]),/DECODE_REJECTED/);
  await assert.rejects(decodeImages([{...image,naturalWidth:0,decode:()=>Promise.resolve()}]),/CI_IMAGE_DECODE_INVALID/);
  assert.deepEqual(await decodeImages([]),[]);
  const spec=readFileSync(resolve(here,'northstar.spec.mjs'),'utf8');
  assert(spec.includes('await runSettlement({timeoutMs:5000'));
  assert(spec.includes('await stable(page);\n          const focus'));
});
test('CI never auto-blesses screenshots or uses permanent/provider data', () => {
  const spec=readFileSync(resolve(here,'northstar.spec.mjs'),'utf8');
  const server=readFileSync(resolve(here,'server.mjs'),'utf8');
  assert(spec.includes("parsed.origin !== 'http://127.0.0.1:5291'"));
  assert(spec.includes("route.abort('blockedbyclient')"));
  assert(spec.includes("maxDiffPixels") === false); // threshold owned centrally by config
  assert.equal(config.expect.toHaveScreenshot.maxDiffPixels,0);
  assert.equal(config.expect.toHaveScreenshot.threshold,0);
  assert(!server.includes('fetch('));assert(!server.includes('https.request'));
  assert(server.includes('res.writeHead(405)'));
  assert(!server.includes('launchctl'));assert(!server.includes('security find'));
});

function visualFixture(){
 const image=new bundle.PNG({width:96,height:96});
 for(let y=0;y<96;y++)for(let x=0;x<96;x++){
  const photo=x>=16&&x<80&&y>=16&&y<80;
  const text=y>=84&&y<89&&x>=4&&x<36&&x%6<3;
  const value=photo?Math.round(110+45*Math.sin(x*.7+y*.4)+35*Math.cos(y*.6)):text?220:30;
  image.data.set([value,Math.min(255,value+5),value,255],(y*96+x)*4);
 }
 const bytes=bundle.PNG.sync.write(image);
 return {bytes,regions:{images:[{x:16,y:16,width:64,height:64}],text:[{x:4,y:84,width:32,height:5}]},
  edit:fn=>{const next=bundle.PNG.sync.read(bytes);fn(next,image);return bundle.PNG.sync.write(next)}};
}
test('perceptual: low-magnitude text antialias and image-edge variance accepted',()=>{
 const f=visualFixture();
 const actual=f.edit(a=>{a.data[(84*96+6)*4]++;for(let y=20;y<70;y++)a.data[(y*96+30)*4]++;});
 const result=compareWebKit(f.bytes,actual,f.regions);
 assert(result.ok,JSON.stringify(result.failures));assert.equal(result.unclassified,0);
});
test('perceptual: shifted elements and changed wrapping rejected',()=>{
 const f=visualFixture();
 for(const offset of [.5,1,3]){
  const moved=f.edit((a,b)=>{for(let y=18;y<78;y++)for(let x=20;x<78;x++)for(let c=0;c<3;c++){const i=(y*96+x)*4+c;const shift=Math.floor(offset),fraction=offset-shift;a.data[i]=Math.round(b.data[i-shift*4]*(1-fraction)+b.data[i-(shift+1)*4]*fraction);}});
  assert(!compareWebKit(f.bytes,moved,f.regions).ok,'shift '+offset);
 }
 const wrapped=f.edit((a,b)=>{for(let y=84;y<89;y++)for(let x=4;x<36;x++){const i=(y*96+x)*4;a.data.set([30,35,30,255],i);a.data.set(b.data.subarray(i,i+4),((y+5)*96+x)*4);}});
 assert(!compareWebKit(f.bytes,wrapped,f.regions).ok);
});
test('perceptual: missing text/control, clipping and obstruction rejected',()=>{
 const f=visualFixture();
 const missing=f.edit(a=>{for(let y=84;y<89;y++)for(let x=4;x<36;x++)a.data.set([30,35,30,255],(y*96+x)*4);});
 assert(!compareWebKit(f.bytes,missing,f.regions).ok);
 const clipped=f.edit(a=>{for(let y=16;y<80;y++)for(let x=16;x<20;x++)a.data.set([30,35,30,255],(y*96+x)*4);});
 assert(!compareWebKit(f.bytes,clipped,f.regions).ok);
 const covered=f.edit(a=>{for(let y=30;y<60;y++)for(let x=30;x<60;x++)a.data.set([0,0,0,255],(y*96+x)*4);});
 assert(!compareWebKit(f.bytes,covered,f.regions).ok);
});
test('perceptual: materially changed colors and broad low-magnitude regions rejected',()=>{
 const f=visualFixture();
 const colored=f.edit(a=>{for(let y=16;y<80;y++)for(let x=16;x<80;x++)for(let c=0;c<3;c++)a.data[(y*96+x)*4+c]+=12;});
 assert(!compareWebKit(f.bytes,colored,f.regions).ok);
 const broad=f.edit(a=>{for(let p=0;p<96*96;p++)a.data[p*4]++;});
  assert(!compareWebKit(f.bytes,broad,f.regions).ok);
  const patch=f.edit(a=>{for(let y=32;y<40;y++)for(let x=32;x<40;x++)for(let c=0;c<3;c++)a.data[(y*96+x)*4+c]+=24;});
  const result=compareWebKit(f.bytes,patch,f.regions);
  assert(!result.ok);assert(result.failures.includes('IMAGE_LOCAL_COLOR_BIAS'),'small colored blocks must not hide in image-wide mean');
});
test('perceptual: repeated inputs deterministic, exact alpha and dimensions',()=>{
 const f=visualFixture();assert.deepEqual(compareWebKit(f.bytes,f.bytes,f.regions),compareWebKit(f.bytes,f.bytes,f.regions));
 assert(compareWebKit(f.bytes,f.bytes,f.regions).ok);
 const alpha=f.edit(a=>{a.data[(30*96+30)*4+3]--;});assert(!compareWebKit(f.bytes,alpha,f.regions).ok);
 assert.throws(()=>compareWebKit(f.bytes,bundle.PNG.sync.write(new bundle.PNG({width:97,height:96})),f.regions),/WIDTH_CHANGED/);
  assert(Object.isFrozen(limits));
  assert.equal(limits.imageChannel,32);
  const abovePeak=f.edit(a=>{a.data[(30*96+30)*4]+=33;});
  assert(!compareWebKit(f.bytes,abovePeak,f.regions).ok,'a sparse 33-channel error must not hide in the low mean');
});
test('structural gate: exact geometry, content, wrapping, style, identity and safety',()=>{
 const before={overflow:0,clipped:[],overlaps:[],obstruction:[],dialog:[],decoration:[],binding:{status:'CURRENT',generation:'fixed'},text:[{value:'required',rects:[[1,2,30,10]]}],controls:[{name:'close',enabled:true}],images:[],style:{fontSize:16}};
 assert.doesNotThrow(()=>assertStructure(before,structuredClone(before)));
 for(const key of ['clipped','overlaps','obstruction','dialog','decoration']){const after=structuredClone(before);after[key]=['defect'];assert.throws(()=>assertStructure(before,after));}
 for(const mutate of [a=>a.overflow=1,a=>a.text=[],a=>a.controls=[],a=>a.controls[0].enabled=false,a=>a.text[0].rects[0][0]+=.5,a=>a.text[0].rects.push([1,12,30,10]),a=>a.text[0].value='changed',a=>a.style.fontSize=17,a=>a.binding.generation='other']){
  const after=structuredClone(before);mutate(after);assert.throws(()=>assertStructure(before,after));
 }
});
