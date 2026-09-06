/// <reference types="node" />
import assert from "node:assert/strict";
import test from "node:test";
import { adaptExpansionSnapshot } from "./TruthSourceAdapter.ts";

const snapshot = { schema_version: "expansion-wing-truth-v1", sections: { projection_freshness: { state: "CURRENT", data: {} }, service_health: { state: "CURRENT", data: {} }, candidate_conveyor: { state: "AVAILABLE_EMPTY", data: { candidate_count: 8 } }, books: { state: "CURRENT", data: { cash: 10_000 } }, multi_asset_factory: { state: "CURRENT", data: { consolidated_paper_nav: 10_000 } }, benchmark_9h: { state: "INCOMPLETE", data: {} } }, authority: { paper_mode: true, credential_access: false, ledger_write_authority: false, broker_connectivity: false, live_execution_authority: false } } as const;

test("pure adapter creates no identity from aggregate counts", () => {
  const result = adaptExpansionSnapshot(snapshot, "CURRENT", 2);
  assert.deepEqual((result.data.factory as Record<string, unknown>).payload, { recent_events: [], cases: [] });
  assert.equal((result.data.safety as Record<string, unknown>).live_execution, false);
});

test("stale and unsafe snapshots freeze presentation truth", () => {
  assert.equal((adaptExpansionSnapshot(snapshot, "STALE", 901).data.freshness as Record<string, unknown>).state, "STALE");
  const unsafe = { ...snapshot, authority: { ...snapshot.authority, live_execution_authority: true } };
  assert.equal(adaptExpansionSnapshot(unsafe, "CURRENT", 0).data.availability, "SOURCE_CONFLICT");
});
