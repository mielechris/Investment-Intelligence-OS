// Static owner-only fixture preview: no proxy, filesystem API or control endpoint.
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { here, inventory, sha } from './prepare.mjs';

const root = resolve(here, '.build');
process.umask(0o077);
const artifacts = resolve(here, process.env.NORTHSTAR_ARTIFACTS || 'artifacts/run');
assert(artifacts.startsWith(resolve(here,'artifacts')+'/'), 'ARTIFACT_ROOT_REQUIRED');
mkdirSync(artifacts, {recursive:true,mode:0o700});
const contract = JSON.parse(readFileSync(resolve(root, 'contract.json')));
assert.equal(sha(JSON.stringify(contract.manifest)), contract.manifestHash);
assert.deepEqual(inventory(resolve(root, 'a')), contract.manifest.outputs);
const files = new Map(contract.manifest.outputs.map(row => ['/review/' + row.path, readFileSync(resolve(root, 'a', row.path))]));
const mime = { html: 'text/html', js: 'text/javascript', css: 'text/css', webp: 'image/webp', svg: 'image/svg+xml' };
const phases = Object.keys(contract.fixtures);
function bootstrap(phase) {
  const fixture=contract.fixtures[phase];
  return contract.geometry.FIXTURE_BOOTSTRAP.replace('FIXTURE_BINDING', JSON.stringify({
    fixture_sha256:sha(JSON.stringify(fixture)), generation:fixture.source_generation,
    source_cycle:fixture.source_cycle, projection_content_hash:fixture.factory.content_hash,
    generated_at:fixture.published_at, clock_ms:Date.parse(fixture.published_at),
  }));
}
const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1:5291');
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
  const referer=req.headers.referer ? new URL(req.headers.referer,'http://127.0.0.1:5291') : null;
  const selected=url.searchParams.get('fixture') || (url.pathname==='/truth-spine/full-session'&&referer?.origin==='http://127.0.0.1:5291' ? referer.searchParams.get('fixture') : null);
  if(selected!==null&&!phases.includes(selected)){res.writeHead(404);res.end();return}
  const phase = selected || phases[0];
  const fixture = contract.fixtures[phase];
  let status = 200, body, type = 'text/plain';
  if (url.pathname === '/truth-spine/full-session') { body = Buffer.from(JSON.stringify(fixture)); type = 'application/json'; }
  else if(url.pathname==='/review/fixture-clock.js'){body=Buffer.from(bootstrap(phase));type='text/javascript'}
  else if (files.has(url.pathname)) {
    body = files.get(url.pathname); type = mime[url.pathname.split('.').at(-1)] || 'application/octet-stream';
    if(url.pathname==='/review/northstar-session.html') {
      assert.equal(body.toString().split('<head>').length,2);
      body=Buffer.from(body.toString().replace('<head>','<head><script src="/review/fixture-clock.js?fixture='+phase+'"></script>'));
    }
  }
  else { status = 404; body = Buffer.from('NOT_FOUND'); }
  // Explicit fixture-only HTML wrapper, identical in CI and the short native
  // smoke. Packaged HTML, JS, CSS and images remain byte-identical on disk.
  res.writeHead(status, { 'Content-Type': type, 'Content-Length': body.length, 'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'" });
  res.end(req.method === 'HEAD' ? undefined : body);
});
server.listen({ host: '127.0.0.1', port: 5291, exclusive: true }, () => {
  writeFileSync(resolve(artifacts, 'server-owner.json'), JSON.stringify({ pid: process.pid, parent: process.ppid, start: new Date().toISOString(), manifest: contract.manifestHash, address: server.address(), fixtureWrappers:Object.fromEntries(phases.map(phase=>[phase,sha(bootstrap(phase))])) }), { mode: 0o600, flag:'wx' });
});
for (const signal of ['SIGINT','SIGTERM']) process.once(signal, () => server.close(() => process.exit(0)));
