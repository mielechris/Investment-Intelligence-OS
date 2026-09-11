// Read-only hosted-rendering metadata. Missing identities are never inferred.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, readdirSync, lstatSync, realpathSync, existsSync, mkdirSync, symlinkSync } from 'node:fs';
import { resolve, relative, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const here = dirname(fileURLToPath(import.meta.url));
export const source = resolve(here, '../..');
export const sha = bytes => createHash('sha256').update(bytes).digest('hex');
export function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]));
  return value;
}
export const hashObject = value => sha(JSON.stringify(canonical(value)));
export function immutable(path, data) {
  const bytes = Buffer.from(JSON.stringify(data, null, 2) + '\n');
  writeFileSync(path, bytes, { flag: 'wx', mode: 0o600 });
  return sha(bytes);
}
export function fileInventory(root, allowedRoots = [realpathSync(root)]) {
  assert(!lstatSync(root).isSymbolicLink(), 'INVENTORY_ROOT_SYMLINK');
  const base = realpathSync(root), rows = [];
  function walk(dir) {
    for (const name of readdirSync(dir).sort()) {
      const path = resolve(dir, name), stat = lstatSync(path), local = relative(base, path);
      if (stat.isSymbolicLink()) {
        const target = realpathSync(path);
        assert(allowedRoots.some(root => target === root || target.startsWith(root + '/')), 'EXTERNAL_INVENTORY_SYMLINK');
        rows.push({ path: local, target: relative(base, target), kind: 'internal-symlink' });
      } else if (stat.isDirectory()) walk(path);
      else {
        assert(stat.isFile(), 'SPECIAL_INVENTORY_FILE');
        const bytes = readFileSync(path);
        rows.push({ path: local, bytes: bytes.length, sha256: sha(bytes) });
      }
    }
  }
  walk(base); return rows;
}
export const requiredSettings = Object.freeze({
  os: '26.6.2', build: '25G83', architecture: 'arm64', imageVersion: '20260831.0337.3',
  node: 'v24.19.0', npm: '11.17.0', python: 'Python 3.14.7', playwright: '1.63.0', webkitRevision: '2359', webkitVersion: '26.6',
});
export function admitSettings(actual, expectedSource) {
  assert(/^[a-f0-9]{40}$/.test(expectedSource || ''), 'INDEPENDENT_SOURCE_PIN_REQUIRED');
  assert.equal(actual.source, expectedSource, 'SOURCE_PIN_MISMATCH');
  for (const [key, value] of Object.entries(requiredSettings)) assert.equal(actual[key], value, 'ENVIRONMENT_PIN_MISMATCH:' + key);
}
function command(program, args) {
  return execFileSync(program, args, { cwd: source, encoding: 'utf8', timeout: 60000, maxBuffer: 64 * 1024 * 1024 }).trim();
}
export function collectEnvironment(root, expectedSource) {
  assert(process.env.GITHUB_ACTIONS === 'true' && process.env.RUNNER_ENVIRONMENT === 'github-hosted' && process.platform === 'darwin', 'HOSTED_MACOS_ONLY');
  const rootPath = realpathSync(root);
  assert(rootPath.startsWith(realpathSync(here) + '/artifacts/requalification-'), 'REVIEW_ROOT_REQUIRED');
  const browserRoot = resolve(process.env.PLAYWRIGHT_BROWSERS_PATH || '', 'webkit-2359');
  assert(browserRoot.startsWith(resolve(here, 'node_modules/.cache/browsers') + '/'), 'ISOLATED_BROWSER_ROOT_REQUIRED');
  const browser = JSON.parse(readFileSync(resolve(here, 'node_modules/playwright-core/browsers.json'))).browsers.find(x => x.name === 'webkit');
  const settings = {
    source: command('git', ['rev-parse', 'HEAD']), os: command('sw_vers', ['-productVersion']), build: command('sw_vers', ['-buildVersion']),
    architecture: process.arch, image: process.env.ImageOS, imageVersion: process.env.ImageVersion,
    node: process.version, npm: command('npm', ['--version']), python: command('python3', ['--version']),
    playwright: JSON.parse(readFileSync(resolve(here, 'node_modules/playwright/package.json'))).version,
    webkitRevision: browser.revision, webkitVersion: browser.browserVersion,
  };
  // Always save observations before failing a pin, including allocation drift.
  immutable(resolve(root, 'allocation.json'), { schema: 'webkit-allocation-v1', settings, expected: { ...requiredSettings, source: expectedSource } });
  admitSettings(settings, expectedSource);
  assert.equal(command('git', ['status', '--porcelain=v1', '--untracked-files=no']), '', 'DIRTY_TRACKED_SOURCE');
  const paths = command('git', ['ls-files', '-z']).split('\0').filter(Boolean).sort();
  const inputs = paths.map(path => ({ path, sha256: sha(readFileSync(resolve(source, path))) }));
  const binaries = fileInventory(browserRoot);
  const fontRoots = ['/System/Library/Fonts', '/Library/Fonts'].filter(existsSync).map(path => realpathSync(path));
  const fonts = fontRoots.flatMap(path => fileInventory(path, fontRoots).map(row => ({ ...row, path: path + '/' + row.path })));
  assert(fonts.length, 'FONT_INVENTORY_MISSING');
  const fontCatalogue = JSON.parse(command('system_profiler', ['SPFontsDataType', '-json']));
  let graphics;
  try { graphics = { status: 'OBSERVED', data: JSON.parse(command('system_profiler', ['SPDisplaysDataType', '-json'])) }; }
  catch (error) { graphics = { status: 'UNAVAILABLE', reason: String(error.message).slice(0, 300) }; }
  const data = {
    schema: 'webkit-hosted-environment-v1', scope: 'REVIEW_ONLY', settings,
    run: { id: process.env.GITHUB_RUN_ID, attempt: process.env.GITHUB_RUN_ATTEMPT, workflowSha: process.env.GITHUB_WORKFLOW_SHA },
    inputs, sourceInventoryHash: hashObject(inputs), browserFiles: binaries, browserInventoryHash: hashObject(binaries),
    nodeBinaryHash: sha(readFileSync(process.execPath)), fonts, fontInventoryHash: hashObject(fonts), fontCatalogue, graphics,
    resolvedBrowserFonts: { status: 'NOT_EXPOSED_BY_PUBLIC_PLAYWRIGHT_WEBKIT_API', faces: null, limitation: 'CSS stacks and the OS catalogue do not establish the face used for each glyph.' },
    immutableOSImageDigest: null, physicalGPUIdentity: null, physicalColorProfileIdentity: null,
    capture: { viewports: [[1512, 825], [1020, 825], [386, 825]], dpr: 1, scale: 'css', locale: 'en-US', timezone: 'UTC', colorScheme: 'dark', reducedMotion: 'reduce', headless: true, workers: 3, retries: 0 },
  };
  immutable(resolve(root, 'environment.json'), data);
  return data;
}
export function preservation(environment) {
  const browserRoot = resolve(process.env.PLAYWRIGHT_BROWSERS_PATH, 'webkit-2359');
  assert.equal(hashObject(fileInventory(browserRoot)), environment.browserInventoryHash, 'BROWSER_FILES_CHANGED');
  const fontRoots = ['/System/Library/Fonts', '/Library/Fonts'].filter(existsSync).map(path => realpathSync(path));
  const fonts = fontRoots.flatMap(path => fileInventory(path, fontRoots).map(row => ({ ...row, path: path + '/' + row.path })));
  assert.equal(hashObject(fonts), environment.fontInventoryHash, 'FONT_FILES_CHANGED');
  for (const input of environment.inputs) assert.equal(sha(readFileSync(resolve(source, input.path))), input.sha256, 'SOURCE_OR_BASELINE_CHANGED:' + input.path);
  return { source: true, baselines: true, browserFiles: true, fontFiles: true };
}
export function selfTest(testRoot) {
  assert(realpathSync(testRoot).startsWith('/private/tmp/iios-sb38d-source-tests-'), 'AUTHORIZED_TEST_ROOT_REQUIRED');
  const actual = { ...requiredSettings, source: 'a'.repeat(40) };
  admitSettings(actual, actual.source);
  assert.throws(() => admitSettings(actual, undefined), /SOURCE_PIN_REQUIRED/);
  assert.throws(() => admitSettings(actual, 'b'.repeat(40)), /SOURCE_PIN_MISMATCH/);
  for (const key of Object.keys(requiredSettings)) assert.throws(() => admitSettings({ ...actual, [key]: 'wrong' }, actual.source), /ENVIRONMENT_PIN_MISMATCH/);
  const dir = resolve(testRoot, 'environment-self-test'); mkdirSync(dir);
  immutable(resolve(dir, 'receipt.json'), { x: 1 });
  assert.throws(() => immutable(resolve(dir, 'receipt.json'), { x: 2 }), /EEXIST/);
  assert.equal(fileInventory(dir).length, 1);
  symlinkSync(testRoot, resolve(dir, 'outside'));
  assert.throws(() => fileInventory(dir), /EXTERNAL_INVENTORY_SYMLINK/);
  assert.equal(hashObject({ b: 2, a: 1 }), hashObject({ a: 1, b: 2 }));
  console.log(JSON.stringify({ suite: 'requalification-environment', passed: Object.keys(requiredSettings).length + 7, failed: 0 }));
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  assert.equal(process.argv[2], '--self-test', 'EXPLICIT_SELF_TEST_ONLY'); selfTest(process.argv[3]);
}
