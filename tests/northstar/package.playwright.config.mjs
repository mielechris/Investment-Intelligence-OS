import { defineConfig } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { contentHash } from './package-contract.mjs';

const file=process.env.NORTHSTAR_PACKAGE_CONTRACT;
assert(file && process.env.NORTHSTAR_PACKAGE_EVIDENCE,'EXPLICIT_PACKAGE_RUN_REQUIRED');
const contract=JSON.parse(fs.readFileSync(file));
assert.equal(contentHash(contract),process.env.NORTHSTAR_PACKAGE_CONTRACT_HASH);
assert.equal(contract.fixtureOnly,false);
assert(!process.argv.some(s=>s.startsWith('--update-snapshots')),'BASELINE_UPDATE_FORBIDDEN');
export default defineConfig({
  testDir:path.dirname(new URL(import.meta.url).pathname),testMatch:'package.acceptance.mjs',
  workers:1,fullyParallel:false,retries:0,forbidOnly:true,timeout:120000,globalTimeout:1800000,
  outputDir:path.join(process.env.NORTHSTAR_PACKAGE_EVIDENCE,'results'),
  reporter:[['line'],['json',{outputFile:path.join(process.env.NORTHSTAR_PACKAGE_EVIDENCE,'results.json')}]],
  use:{baseURL:contract.origin,headless:true,locale:'en-US',timezoneId:'UTC',deviceScaleFactor:1,
    reducedMotion:'reduce',serviceWorkers:'block',trace:'on',screenshot:'only-on-failure'},
  projects:['chromium','firefox','webkit'].map(browserName=>({name:browserName,use:{browserName}})),
});
