// Package acceptance has no fixture imports, clock bootstrap or response substitution.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

export const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
export function canonical(value) {
  function sorted(v) {
    if (typeof v === 'number') assert(Number.isSafeInteger(v), 'CANONICAL_INTEGER_REQUIRED');
    if (Array.isArray(v)) return v.map(sorted);
    if (v !== null && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])]));
    assert(v === null || ['string', 'number', 'boolean'].includes(typeof v), 'CANONICAL_VALUE_REQUIRED');
    return v;
  }
  return JSON.stringify(sorted(value)).replace(/[\u007f-\uffff]/g, c => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`) + '\n';
}
export const digest = value => sha(canonical(value));
export const contentHash = value => digest(Object.fromEntries(Object.entries(value).filter(([k]) => k !== 'content_hash')));
export function safeFile(root, relative) {
  assert(path.isAbsolute(root) && !relative.split('/').includes('..') && !path.isAbsolute(relative), 'RELATIVE_PATH_REQUIRED');
  const file = path.resolve(root, relative);
  assert(file.startsWith(root + '/'), 'ROOT_ESCAPE');
  for (let p = file; ; p = path.dirname(p)) {
    assert(!fs.lstatSync(p).isSymbolicLink(), 'SYMLINK_REJECTED');
    if (p === path.dirname(p)) break;
  }
  assert(fs.lstatSync(file).isFile(), 'REGULAR_FILE_REQUIRED');
  return file;
}
export function pinnedJSON(root, relative, expected) {
  assert(/^[a-f0-9]{64}$/.test(expected), 'INDEPENDENT_PIN_REQUIRED');
  const bytes = fs.readFileSync(safeFile(root, relative));
  assert.equal(sha(bytes), expected, 'FILE_PIN_MISMATCH');
  return JSON.parse(bytes);
}
export function newJSON(file, value) {
  fs.writeFileSync(file, canonical(value), { flag: 'wx', mode: 0o400 });
}
export function geometrySource(source) {
  return ['TEXT_GEOMETRY','DIALOG_GEOMETRY','OBSTRUCTION_GEOMETRY','SETTLEMENT_GEOMETRY'].map(name=>{
    const marker=name+' = r"""';
    assert.equal(source.split(marker).length,2,'GEOMETRY_SOURCE_REQUIRED');
    return source.split(marker)[1].split('"""')[0];
  }).join('\n');
}
export function geometryEvaluation(source, probe, argument=null) {
  // Evaluate the pinned algorithms and probe in one local scope. Helpers never
  // depend on declarations leaking from a previous page.evaluate call.
  assert.equal(typeof source,'string');assert.equal(typeof probe,'function');
  return `(() => {\n${source}\nreturn (${probe.toString()})({runSettlement,geometryFrame,requiredText,obstructionCensus,headingTypography},${JSON.stringify(argument)});\n})()`;
}
export function makeContract(root, manifestHash, backendHash, origin, sourceCommit, toolsFile, toolsHash) {
  assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(origin), 'ISOLATED_ORIGIN_REQUIRED');
  assert(![5176,5177,5184,5185,5186,5291,5292,8002].includes(Number(new URL(origin).port)), 'PROTECTED_PORT');
  const m = pinnedJSON(root, 'release/manifest.json', manifestHash);
  assert.equal(m.schema, 'iios-historical-package-v2');
  assert.equal(m.source_base, sourceCommit);
  assert.equal(m.content_hash, contentHash(m));
  const docs = Object.fromEntries(['input_spec','admission','generation','events','initial_cycle'].map(k => {
    const row=m.lineage[k]; return [k,pinnedJSON(root,row.path,row.sha256)];
  }));
  const runtime = pinnedJSON(root,'runtime/runtime-manifest.json',m.dependency_hash);
  assert.equal(runtime.source_commit,sourceCommit); assert.equal(runtime.installed_root,root);
  assert.equal(runtime.interpreter_relative,'runtime/bin/python');
  assert.equal(runtime.package_generation,m.lineage.package_generation);
  for (const [base,rows] of [['release',m.files],['runtime',m.runtime_files]]) for (const row of rows) {
    const bytes=fs.readFileSync(safeFile(root,base+'/'+row.path));
    assert.equal(bytes.length,row.bytes); assert.equal(sha(bytes),row.sha256);
  }
  const a=docs.admission,g=docs.generation;
  const backendStartup=JSON.parse(fs.readFileSync(safeFile(root,'state/backend-instance.json')));
  assert.equal(contentHash(backendStartup),backendHash);assert.equal(backendStartup.content_hash,backendHash);
  assert.equal(backendStartup.role,'backend');assert.equal(backendStartup.root_hash,digest(root));
  assert.equal(backendStartup.port,Number(new URL(origin).port));
  assert.equal(backendStartup.topology_hash,sha(fs.readFileSync(safeFile(root,'topology.json'))));
  const toolBytes=fs.readFileSync(toolsFile);assert.equal(sha(toolBytes),toolsHash,'BROWSER_TOOLS_PIN_MISMATCH');
  const toolchain=JSON.parse(toolBytes),browserExecutables={};
  browserExecutables[toolchain.node.path]=toolchain.node.sha256;
  for(const row of toolchain.cache.files)browserExecutables[row.pin.path]=row.pin.sha256;
  for(const name of ['package-contract.mjs','package-run.mjs','package.acceptance.mjs','package.playwright.config.mjs'])
    assert.equal(sha(fs.readFileSync(safeFile(toolchain.harness.root,name))),sha(fs.readFileSync(safeFile(root,'release/proof-sources/'+name))),'BROWSER_HARNESS_SOURCE_MISMATCH');
  assert.equal(a.content_hash,contentHash(a)); assert.equal(g.content_hash,contentHash(g));
  assert.equal(g.identity,a.content_hash); assert.equal(g.events_hash,digest({events:docs.events}));
  const expected = {
    source_commit:sourceCommit,package_hash:manifestHash,package_generation:m.lineage.package_generation,
    runtime_hash:m.dependency_hash,frontend_hash:m.frontend_content_hash,admission_hash:a.content_hash,
    generation_hash:g.content_hash,initial_cycle_hash:m.lineage.initial_cycle.sha256,
    owner_manifest_hash:a.files['manifest.json'].source_sha256,completion_hash:a.files['completion-receipt.json'].source_sha256,
    l7_hash:a.files['l7/snapshot.db'].source_sha256,l8_hash:a.files['l8/snapshot.db'].source_sha256,
    backend_instance_hash:backendHash,common_watermark:a.common_watermark,classification:'HISTORICAL_REPLAY',
  };
  assert(/^[a-f0-9]{64}$/.test(backendHash),'BACKEND_PIN_REQUIRED');
  const contract = {schema:'iios-northstar-package-contract-v1',fixtureOnly:false,origin,packageRoot:root,backendStartup,browserExecutables,toolsHash,
    expected,outputs:m.frontend_provenance.outputs,cycleBasis:docs.initial_cycle,
    generation:g,sourceInputsHash:m.frontend_input_hash,
    geometry:geometrySource(fs.readFileSync(safeFile(root,'release/proof-sources/truth_spine_northstar_browser.py'),'utf8'))};
  return {...contract,content_hash:digest(contract)};
}
export function verifyView(view, contract, now=Date.now()) {
  assert.equal(contract.content_hash,contentHash(contract)); assert.equal(contract.fixtureOnly,false);
  assert.equal(view.schema,'iios-historical-northstar-browser-v2');
  assert.equal(view.scope,'HISTORICAL_REPLAY_NOT_CURRENT_MARKET'); assert.equal(view.phase,'SESSION_CLOSED');
  assert.equal(view.readiness,200); assert.equal(view.capture_status,'CURRENT');
  const age=now-Date.parse(view.published_at); assert(age>=0 && age<=15000,'STALE_PUBLICATION');
  for (const [k,v] of Object.entries(contract.expected)) assert.deepEqual(view.lineage[k],v,'LINEAGE_'+k);
  assert.equal(view.source_generation,contract.expected.generation_hash);
  assert.equal(view.owners.backend_owner,contract.expected.backend_instance_hash,'BACKEND_OWNER_MISMATCH');
  assert.equal(view.factory.content_hash,contentHash(view.factory));
  assert.equal(view.lineage.projection_hash,view.factory.content_hash);
  const cycle={...contract.cycleBasis,published_at:view.published_at,package_hash:contract.expected.package_hash};
  delete cycle.source_cycle_id;
  assert.equal(view.source_cycle,digest(cycle)); assert.equal(view.lineage.source_cycle,view.source_cycle);
  assert.equal(view.factory.source_cycle_id,view.source_cycle);
  assert(Object.values(view.capabilities).every(x=>x===false),'AUTHORITY_ENABLED');
  assert(Object.values(view.counters).every(x=>x===0),'RESTRICTED_ACTIVITY');
  return {response_hash:digest(view),projection_hash:view.factory.content_hash,source_cycle:view.source_cycle,
    generation:view.source_generation,backend:contract.expected.backend_instance_hash,contract:contract.content_hash};
}
