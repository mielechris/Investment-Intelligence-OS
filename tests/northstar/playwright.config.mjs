import { defineConfig } from '@playwright/test';
process.umask(0o077);
const artifacts = process.env.NORTHSTAR_ARTIFACTS || 'artifacts/run';
if (process.env.CI && process.argv.some(x => x.startsWith('--update-snapshots'))) throw Error('CI_BASELINE_UPDATE_PROHIBITED');
export default defineConfig({
  testDir: '.', testMatch: '*.spec.mjs', testIgnore: ['**/artifacts/**', '**/node_modules/**'], fullyParallel: true, workers: 3, retries: 0,
  timeout: 180000, globalTimeout: 3600000, forbidOnly: true,
  outputDir: artifacts + '/results',
  reporter: [['line'], ['json', { outputFile: artifacts + '/results.json' }], ['html', { outputFolder: artifacts + '/report', open: 'never' }]],
  snapshotPathTemplate: '{testDir}/snapshots/{platform}/{projectName}/{arg}{ext}',
  expect: { timeout: 10000, toMatchSnapshot: { maxDiffPixels: 0, threshold: 0 }, toHaveScreenshot: { animations: 'disabled', caret: 'hide', maxDiffPixels: 0, threshold: 0 } },
  use: { headless: true, baseURL: 'http://127.0.0.1:5291', locale: 'en-US', timezoneId: 'UTC',
    colorScheme: 'dark', reducedMotion: 'reduce', deviceScaleFactor: 1, serviceWorkers: 'block',
    trace: 'on', screenshot: 'only-on-failure' },
  projects: ['chromium','firefox','webkit'].map(browserName => ({ name: browserName, use: { browserName } })),
  webServer: { command: 'node server.mjs', url: 'http://127.0.0.1:5291/review/northstar-session.html', reuseExistingServer: false, timeout: 10000, gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 } },
});
