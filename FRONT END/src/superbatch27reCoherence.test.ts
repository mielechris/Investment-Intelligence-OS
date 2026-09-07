import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const source = fs.readFileSync(path.join(process.cwd(), "src/ExpansionWingSnapshotProvider.tsx"), "utf8");

test("controller snapshots replace atomically and reject older reads", () => {
  assert.match(source, /controller_generation_sequence/);
  assert.match(source, /controller_read_timestamp/);
  assert.match(source, /readAt < prior\.readAt/);
  assert.match(source, /setSnapshot\(payload\)/);
  assert.doesNotMatch(source, /setSnapshot\([^)]*\.\.\./);
});

test("a later read may carry an older rollback sequence", () => {
  assert.match(source, /readAt === prior\.readAt && sequence < prior\.sequence/);
  assert.doesNotMatch(source, /sequence < prior\.sequence\) return/);
});
