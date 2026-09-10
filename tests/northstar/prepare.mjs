// Offline fixture/build preparation. No operational module or state root is loaded.
import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, lstatSync, existsSync } from 'node:fs';
import { resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { northstarFixture } from '../../FRONT END/src/northstarSession.fixture.ts';
import { contentHash, admitProjection } from '../../FRONT END/src/northstarSession.ts';
import { sessionPhases } from '../../FRONT END/src/truthSpineSessionView.ts';
import { AUCTION_ROOMS } from '../../FRONT END/src/auctionRegistry.ts';

export const here = dirname(fileURLToPath(import.meta.url));
export const source = resolve(here, '../..');
export const sha = data => createHash('sha256').update(data).digest('hex');
export function inventory(root) {
  return readdirSync(root, { recursive: true }).sort().flatMap(name => {
    const path = resolve(root, name);
    assert(!lstatSync(path).isSymbolicLink(), 'SYMLINK_REJECTED');
    if (statSync(path).isDirectory()) return [];
    assert(statSync(path).isFile(), 'SPECIAL_FILE_REJECTED');
    const bytes = readFileSync(path);
    return [{ path: name, bytes: bytes.length, sha256: sha(bytes) }];
  });
}
export async function fixtures() {
  const at = Date.parse('2026-09-11T13:30:00Z');
  const values = {};
  for (const phase of sessionPhases) {
    const view = await northstarFixture(at);
    view.phase = phase; view.factory.phase = phase;
    for (const group of ['rooms', 'agents', 'governance', 'routes', 'history', 'subsystems'])
      for (const row of view.factory[group]) row.phase = phase;
    view.factory.day_trading.phase = phase;
    view.factory.content_hash = await contentHash(view.factory);
    await admitProjection(view, null, at);
    values[phase] = view;
  }
  return values;
}
export async function prepare() {
  process.umask(0o077);
  const root = resolve(here, '.build');
  assert(!existsSync(root), 'FRESH_BUILD_ROOT_REQUIRED');
  mkdirSync(root, { mode: 0o700 });
  const environment = { PATH: process.env.PATH, NODE_ENV: 'production', TZ: 'UTC', LANG: 'C', LC_ALL: 'C', VITE_NORTHSTAR_FULL_SESSION: '1' };
  const outputs = {};
  for (const name of ['a', 'b']) {
    const out = resolve(root, name);
    execFileSync(process.execPath, ['node_modules/vite/bin/vite.js', 'build', '--configLoader', 'runner', '--base', '/review/', '--outDir', out], {
      cwd: resolve(source, 'FRONT END'), env: environment, stdio: 'inherit', timeout: 120000,
    });
    outputs[name] = inventory(out);
  }
  assert.deepEqual(outputs.a, outputs.b, 'NONDETERMINISTIC_BUILD');
  const geometry = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-B', '-c',
    'import ast,json,sys; t=ast.parse(open(sys.argv[1]).read()); names={"TEXT_GEOMETRY","OBSTRUCTION_GEOMETRY","DIALOG_GEOMETRY","SETTLEMENT_GEOMETRY","DECORATION_GEOMETRY","CAPTURE_IDENTITY","FIXTURE_BOOTSTRAP"}; print(json.dumps({n.targets[0].id:ast.literal_eval(n.value) for n in t.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names}))',
    resolve(source, 'scripts/truth_spine_northstar_browser.py')], { encoding: 'utf8' }));
  assert.equal(Object.keys(geometry).length, 7);
  const values = await fixtures();
  const tracked = execFileSync('git', ['ls-files', '-z', '--', 'FRONT END', 'scripts/truth_spine_northstar_browser.py'], { cwd: source, encoding: 'utf8' }).split('\0');
  const extra = execFileSync('git', ['ls-files', '--others', '--exclude-standard', '-z', '--', 'FRONT END', 'scripts/truth_spine_northstar_browser.py'], { cwd: source, encoding: 'utf8' }).split('\0');
  const inputs = [...new Set([...tracked, ...extra])].filter(Boolean).sort().map(path => ({ path, sha256: sha(readFileSync(resolve(source, path))) }));
  const manifest = { schema: 'iios-northstar-ci-fixture-v1', fixtureOnly: true,
    commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: source, encoding: 'utf8' }).trim(),
    node: process.version, inputs, outputs: outputs.a, environment: { ...environment, PATH: 'TOOLCHAIN_PATH' },
    fixtureHashes: Object.fromEntries(Object.entries(values).map(([phase, value]) => [phase, sha(JSON.stringify(value))])),
    geometryHash: sha(JSON.stringify(geometry)), authorities: 'ALL_FALSE',
  };
  const contract = { manifest, manifestHash: sha(JSON.stringify(manifest)), geometry, fixtures: values, stations: AUCTION_ROOMS.map(({id,label,shortLabel}) => ({id,label,shortLabel})) };
  writeFileSync(resolve(root, 'contract.json'), JSON.stringify(contract, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  console.log(JSON.stringify({ manifestHash: contract.manifestHash, assets: outputs.a.length, root: relative(source, root) }));
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await prepare();
