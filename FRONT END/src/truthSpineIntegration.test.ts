import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
const source = readFileSync(new URL('./TruthSpineIntegrationPreview.tsx', import.meta.url), 'utf8');
test('candidate uses read-only same-origin projection and one polling owner', () => {
  assert.match(source, /fetch\('\/truth-spine\/museum'/);
  assert.equal((source.match(/setTimeout\(poll/g) ?? []).length, 1);
  assert.doesNotMatch(source, /method:\s*['"]POST|api_key|localhost:8002/);
});
test('universe counts are dynamic and source-qualified', () => {
  assert.match(source, /u.count/); assert.doesNotMatch(source, /518-name|517-name/);
  assert.match(source, /not direct official membership/);
});
test('separate clocks, narrative and no-paper terminal remain visible', () => {
  for (const text of ['Event time','Observation time','Publication time','NARRATIVE','NO_PAPER_AUTHORITY','ABSTAINED']) assert.ok(source.includes(text));
  assert.match(source, /age <= 15000/);
});
test('retention never replaces preserved evidence classifications', () => {
  assert.match(source, /view.classification_counts/);
  assert.match(source, /retention_context === 'RETAINED_READ_ONLY'/);
  for (const label of ['REPLAY', 'HISTORICAL', 'SIMULATED', 'NARRATIVE', 'LIVE_VERIFIED', 'UNAVAILABLE', 'STALE']) {
    assert.ok(source.includes(`'${label}'`));
  }
  assert.doesNotMatch(source, /\{count\} historical records/);
  assert.match(source, /Retention is historical context, not evidence classification/);
});
