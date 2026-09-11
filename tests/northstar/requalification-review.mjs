// Review-only extraction. A failed acceptance run remains failed.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdirSync, realpathSync, appendFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync, spawnSync } from 'node:child_process';
import { here, source, sha, hashObject, immutable, collectEnvironment, preservation } from './requalification-environment.mjs';

export const reviewPaths = Object.freeze([
  '.github/workflows/northstar-offline-acceptance.yml',
  'tests/northstar/requalification-environment.mjs',
  'tests/northstar/requalification-review.mjs',
  'tests/northstar/northstar.spec.mjs',
]);
export function route(event, paths, requested) {
  if (event === 'workflow_dispatch') {
    assert(['full', 'review'].includes(requested), 'EXPLICIT_WORKFLOW_MODE_REQUIRED');
    return requested;
  }
  if (event === 'push' && paths.length && paths.every(path => reviewPaths.includes(path))) return 'review';
  return 'full';
}
export function testRows(results) {
  const rows = [];
  function walk(suite, parents = []) {
    const names = [...parents, suite.title || ''];
    for (const spec of suite.specs || []) for (const test of spec.tests) {
      assert.equal(test.projectName, 'webkit', 'WRONG_BROWSER');
      assert.equal(test.results.length, 1, 'MULTIPLE_ATTEMPTS');
      const result = test.results[0];
      assert.equal(result.retry, 0, 'RETRY_REJECTED');
      assert(['passed', 'failed'].includes(result.status), 'INCOMPLETE_TEST:' + result.status);
      rows.push({ title: [...names, spec.title].filter(Boolean).join(' / '), spec: spec.title, result });
    }
    for (const child of suite.suites || []) walk(child, names);
  }
  walk(results);
  assert.equal(rows.length, 84, 'COMPLETE_84_CASE_COLLECTION_REQUIRED');
  return rows;
}
export function verifyParent(bytes, independentlyExpectedHash) {
  assert(/^[0-9a-f]{64}$/.test(independentlyExpectedHash || ''), 'EXPECTED_PARENT_REQUIRED');
  assert.equal(sha(bytes), independentlyExpectedHash, 'PARENT_HASH_MISMATCH');
}
export function compareInventories(a, b) {
  assert.equal(a.length, 54, '54_REFERENCES_REQUIRED'); assert.equal(b.length, 54, '54_REFERENCES_REQUIRED');
  const names = rows => rows.map(x => x.case).sort();
  assert.equal(new Set(names(a)).size, 54, 'DUPLICATE_REFERENCE');
  assert.equal(new Set(names(b)).size, 54, 'DUPLICATE_REFERENCE');
  assert.deepEqual(names(a), names(b), 'CASE_SET_MISMATCH');
  return a.map(x => {
    const y = b.find(y => y.case === x.case);
    return { case: x.case, pngEqual: x.sha256 === y.sha256, rgbaEqual: x.rgbaHash === y.rgbaHash, dimensionsEqual: x.width === y.width && x.height === y.height };
  });
}
export function pngMetadata(bytes) {
  assert(bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')), 'PNG_SIGNATURE');
  const chunks = [];
  let offset = 8, ended = false;
  while (offset < bytes.length) {
    assert(offset + 12 <= bytes.length, 'PNG_CHUNK_TRUNCATED');
    const length = bytes.readUInt32BE(offset), type = bytes.toString('ascii', offset + 4, offset + 8);
    assert(offset + 12 + length <= bytes.length, 'PNG_CHUNK_TRUNCATED');
    if (['sRGB', 'gAMA', 'cHRM', 'iCCP', 'cICP'].includes(type)) chunks.push({ type, length, payloadHash: sha(bytes.subarray(offset + 8, offset + 8 + length)), ...(length <= 32 ? { payloadHex: bytes.subarray(offset + 8, offset + 8 + length).toString('hex') } : {}) });
    offset += length + 12;
    if (type === 'IEND') { ended = true; break; }
  }
  assert(ended && offset === bytes.length, 'PNG_END_REQUIRED');
  return { colorChunks: chunks, physicalDisplayProfile: null };
}
async function extract(root, expectedEnvironmentHash, environment, exitStatus) {
  verifyParent(readFileSync(resolve(root, 'environment.json')), expectedEnvironmentHash);
  const contractBytes = readFileSync(resolve(here, '.build/contract.json')), contract = JSON.parse(contractBytes);
  assert.equal(contract.manifestHash, sha(JSON.stringify(contract.manifest)), 'BUILD_CONTRACT_HASH');
  assert.equal(contract.manifest.commit, environment.settings.source, 'BUILD_SOURCE_MISMATCH');
  assert.equal(contract.manifest.fixtureOnly, true, 'FIXTURE_ONLY_REQUIRED');
  for (const input of contract.manifest.inputs) assert.equal(sha(readFileSync(resolve(source, input.path))), input.sha256, 'BUILD_INPUT_CHANGED');
  for (const output of contract.manifest.outputs) assert.equal(sha(readFileSync(resolve(here, '.build/a', output.path))), output.sha256, 'BUILD_OUTPUT_CHANGED');
  const resultBytes = readFileSync(resolve(root, 'capture/results.json')), results = JSON.parse(resultBytes), rows = testRows(results);
  const ownership = JSON.parse(readFileSync(resolve(root, 'capture/ownership.json')));
  assert.deepEqual(ownership.remaining, [], 'SURVIVING_PROCESS'); assert.deepEqual(ownership.listeners, [], 'SURVIVING_LISTENER');
  assert.equal(ownership.result.code, exitStatus, 'EXECUTOR_EXIT_MISMATCH');
  const { default: bundle } = await import('./node_modules/playwright-core/lib/utilsBundle.js');
  const { assertStructure, compareWebKit, limits } = await import('./webkit-perceptual.mjs');
  const expectedCases = new Set([1512, 1020, 386].flatMap(width => contract.stations.map(s => `${width}-${s.id}`)));
  assert.equal(expectedCases.size, 54, 'EXACT_FIXTURE_CASES_REQUIRED');
  mkdirSync(resolve(root, 'candidate-references'));
  const references = [], cssFonts = new Set();
  for (const row of rows) {
    const attachments = row.result.attachments;
    const network = attachments.find(a => a.name === 'network-and-runtime');
    assert(network?.body, 'NETWORK_EVIDENCE_MISSING');
    const net = JSON.parse(Buffer.from(network.body, 'base64'));
    assert.deepEqual(net.errors, [], 'RUNTIME_ERRORS'); assert.deepEqual(net.forbidden, [], 'FORBIDDEN_REQUESTS');
    assert.equal(net.manifest, contract.manifestHash, 'BROWSER_BUILD_MISMATCH');
    if (!row.spec.startsWith('station ')) continue;
    const comparison = attachments.find(a => a.name.endsWith('-perceptual-comparison'));
    assert(comparison, 'COMPARISON_EVIDENCE_MISSING');
    const name = comparison.name.replace(/-perceptual-comparison$/, '');
    assert(expectedCases.delete(name), 'EXTRA_OR_DUPLICATE_CASE');
    function attachment(suffix) {
      const found = attachments.filter(a => a.name === name + suffix);
      assert.equal(found.length, 1, 'UNIQUE_ATTACHMENT_REQUIRED'); assert(found[0].body, 'INLINE_EVIDENCE_REQUIRED');
      return Buffer.from(found[0].body, 'base64');
    }
    const structure = JSON.parse(attachment('-structural-contract'));
    assertStructure(structure.before, structure.after);
    assert.deepEqual(structure.before.viewport, [Number(name.split('-')[0]), 825, 1], 'VIEWPORT_DPR_MISMATCH');
    assert.equal(structure.before.binding.fixture_sha256, net.fixture, 'FIXTURE_BINDING_MISMATCH');
    assert(Object.values(contract.manifest.fixtureHashes).includes(net.fixture), 'UNKNOWN_FIXTURE');
    structure.before.styles.forEach(x => cssFonts.add(x.style.fontFamily));
    const bytes = attachment('-observed'), expected = attachment('-expected');
    assert.equal(sha(expected), sha(readFileSync(resolve(here, 'snapshots/darwin/webkit', name + '.png'))), 'ORIGINAL_BASELINE_MISMATCH');
    const comparisonData = JSON.parse(Buffer.from(comparison.body, 'base64'));
    const independentlyCompared = compareWebKit(expected, bytes, comparisonData.regions);
    assert.deepEqual(comparisonData.limits, limits, 'COMPARISON_LIMITS_CHANGED');
    const recordedComparison = { ...comparisonData }; delete recordedComparison.limits; delete recordedComparison.regions;
    const recomputedComparison = { ...independentlyCompared }; delete recomputedComparison.diff;
    assert.deepEqual(recomputedComparison, recordedComparison, 'COMPARISON_RESULT_MISMATCH');
    const decoded = bundle.PNG.sync.read(bytes);
    writeFileSync(resolve(root, 'candidate-references', name + '.png'), bytes, { flag: 'wx', mode: 0o600 });
    references.push({ case: name, path: `candidate-references/${name}.png`, bytes: bytes.length, sha256: sha(bytes), rgbaHash: sha(decoded.data), width: decoded.width, height: decoded.height,
      pngMetadata: pngMetadata(bytes), fullViewportMetadata: pngMetadata(attachment('-full-viewport')), originalBaselineHash: sha(expected), structureHash: hashObject(structure), originalComparisonPassed: comparisonData.ok, testStatus: row.result.status });
  }
  assert.equal(expectedCases.size, 0, 'MISSING_REFERENCE');
  references.sort((a, b) => a.case.localeCompare(b.case));
  return { schema: 'webkit-review-candidates-v1', scope: 'REVIEW_ONLY_NOT_ACCEPTANCE', source: environment.settings.source,
    environmentHash: expectedEnvironmentHash, contractHash: sha(contractBytes), manifestHash: contract.manifestHash, resultsHash: sha(resultBytes),
    run: environment.run, exitStatus, originalAcceptancePassed: exitStatus === 0,
    tests: { total: rows.length, passed: rows.filter(x => x.result.status === 'passed').length, failed: rows.filter(x => x.result.status === 'failed').length, retries: 0, skipped: 0 },
    cssFontStacks: [...cssFonts].sort(), resolvedBrowserFaces: null, references };
}
async function capture(pass) {
  assert(['A', 'B'].includes(pass), 'EXPLICIT_PASS_REQUIRED');
  assert(process.env.GITHUB_ACTIONS === 'true' && process.env.RUNNER_ENVIRONMENT === 'github-hosted', 'HOSTED_ONLY');
  assert(/^\d+$/.test(process.env.GITHUB_RUN_ID || '') && /^\d+$/.test(process.env.GITHUB_RUN_ATTEMPT || ''), 'RUN_ID_REQUIRED');
  assert.equal(process.env.GITHUB_RUN_ATTEMPT, '1', 'RETRIED_WORKFLOW_REJECTED');
  assert.equal(process.env.GITHUB_SHA, process.env.NORTHSTAR_EXPECTED_SOURCE, 'WORKFLOW_CANDIDATE_MISMATCH');
  const root = resolve(here, `artifacts/requalification-${process.env.GITHUB_RUN_ID}-${pass}`);
  mkdirSync(resolve(here, 'artifacts'), { recursive: true }); mkdirSync(root, { mode: 0o700 });
  let environment, status, receipt;
  try {
    environment = collectEnvironment(root, process.env.NORTHSTAR_EXPECTED_SOURCE);
    const parentHash = sha(readFileSync(resolve(root, 'environment.json')));
    const result = spawnSync(process.execPath, ['run.mjs', '--project=webkit'], { cwd: here, stdio: 'inherit', env: { ...process.env, NORTHSTAR_ARTIFACTS: resolve(root, 'capture') }, timeout: 35 * 60 * 1000 });
    assert(!result.error && result.signal === null, 'CAPTURE_EXECUTOR_FAILURE');
    status = result.status;
    receipt = await extract(root, parentHash, environment, status);
  } catch (error) {
    immutable(resolve(root, 'capture-failure.json'), { name: error.name, message: error.message });
    status = 1;
  } finally {
    if (environment) {
      try { immutable(resolve(root, 'preservation.json'), preservation(environment)); }
      catch (error) { immutable(resolve(root, 'preservation-failure.json'), { message: error.message }); status = 1; }
    }
  }
  if (receipt) immutable(resolve(root, 'candidate-inventory.json'), receipt);
  immutable(resolve(root, 'execution.json'), { pass, status, candidateCount: receipt?.references.length || 0, acceptance: status === 0 ? 'ORIGINAL_SUITE_PASSED' : 'ORIGINAL_SUITE_OR_REVIEW_GATE_FAILED', adopted: false });
  process.exitCode = status;
}
async function selfTest(root) {
  assert(realpathSync(root).startsWith('/private/tmp/iios-sb38d-source-tests-'), 'AUTHORIZED_TEST_ROOT_REQUIRED');
  let passed = 0;
  const check = fn => { fn(); passed++; };
  check(() => assert.equal(route('push', [...reviewPaths]), 'review'));
  check(() => assert.equal(route('push', [...reviewPaths, 'FRONT END/src/App.tsx']), 'full'));
  check(() => assert.equal(route('push', []), 'full'));
  check(() => assert.equal(route('pull_request', [...reviewPaths]), 'full'));
  check(() => assert.equal(route('workflow_dispatch', [], 'review'), 'review'));
  check(() => assert.throws(() => route('workflow_dispatch', [], 'other')));
  check(() => assert.throws(() => verifyParent(Buffer.from('a'), undefined), /EXPECTED_PARENT/));
  check(() => assert.throws(() => verifyParent(Buffer.from('a'), sha('b')), /PARENT_HASH/));
  check(() => verifyParent(Buffer.from('a'), sha('a')));
  const refs = Array.from({ length: 54 }, (_, i) => ({ case: '' + i, sha256: sha('a'), rgbaHash: sha('b'), width: 2, height: 2 }));
  check(() => assert(compareInventories(refs, refs).every(x => x.pngEqual && x.rgbaEqual && x.dimensionsEqual)));
  check(() => assert.throws(() => compareInventories(refs.slice(1), refs), /54_REFERENCES/));
  check(() => assert.throws(() => compareInventories(refs, [...refs.slice(1), refs[1]]), /DUPLICATE/));
  check(() => assert.equal(compareInventories(refs, refs.map((x, i) => i ? x : { ...x, rgbaHash: sha('c') }))[0].rgbaEqual, false));
  const results = { specs: Array.from({ length: 84 }, () => ({ title: 'synthetic', tests: [{ projectName: 'webkit', results: [{ retry: 0, status: 'passed' }] }] })) };
  check(() => assert.equal(testRows(results).length, 84));
  check(() => assert.throws(() => testRows({ specs: results.specs.slice(1) }), /84_CASE/));
  const retry = structuredClone(results); retry.specs[0].tests[0].results[0].retry = 1;
  check(() => assert.throws(() => testRows(retry), /RETRY/));
  const skipped = structuredClone(results); skipped.specs[0].tests[0].results[0].status = 'skipped';
  check(() => assert.throws(() => testRows(skipped), /INCOMPLETE/));
  const wrongBrowser = structuredClone(results); wrongBrowser.specs[0].tests[0].projectName = 'firefox';
  check(() => assert.throws(() => testRows(wrongBrowser), /WRONG_BROWSER/));
  const multiple = structuredClone(results); multiple.specs[0].tests[0].results.push({ retry: 1, status: 'passed' });
  check(() => assert.throws(() => testRows(multiple), /MULTIPLE_ATTEMPTS/));
  check(() => assert.throws(() => compareInventories(refs, refs.map((x, i) => i ? x : { ...x, case: 'unexpected' })), /CASE_SET/));
  check(() => assert.equal(compareInventories(refs, refs.map((x, i) => i ? x : { ...x, width: 3 }))[0].dimensionsEqual, false));
  const emptyPng = Buffer.from('89504e470d0a1a0a0000000049454e4400000000', 'hex');
  check(() => assert.deepEqual(pngMetadata(emptyPng).colorChunks, []));
  check(() => assert.throws(() => pngMetadata(Buffer.from('not png')), /PNG_SIGNATURE/));
  check(() => assert.throws(() => pngMetadata(emptyPng.subarray(0, 15)), /PNG_CHUNK/));
  immutable(resolve(root, 'review-self-test.json'), { suite: 'requalification-review', passed, failed: 0 });
  console.log(JSON.stringify({ suite: 'requalification-review', passed, failed: 0 }));
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const mode = process.argv[2];
  if (mode === '--self-test') await selfTest(process.argv[3]);
  else if (mode === '--capture') await capture(process.argv[3]);
  else if (mode === '--route') {
    const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH));
    let paths = [];
    if (process.env.GITHUB_EVENT_NAME === 'push' && /^[a-f0-9]{40}$/.test(event.before || '') && !/^0+$/.test(event.before)) {
      paths = execFileSync('git', ['diff', '--name-only', '-z', event.before, process.env.GITHUB_SHA], { cwd: source, encoding: 'utf8' }).split('\0').filter(Boolean);
    }
    const selected = route(process.env.GITHUB_EVENT_NAME, paths, event.inputs?.mode || 'full');
    appendFileSync(process.env.GITHUB_OUTPUT, `mode=${selected}\n`);
    console.log(JSON.stringify({ mode: selected, changedPaths: paths, scope: selected === 'review' ? 'OFFLINE_REVIEW_CHECKS; CAPTURE_ONLY_ON_EXPLICIT_DISPATCH' : 'NORMAL_CI' }));
  } else throw Error('EXPLICIT_MODE_REQUIRED');
}
