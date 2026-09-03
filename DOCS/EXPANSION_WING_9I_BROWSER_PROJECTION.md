# Batch 9I browser-safe projection

## Producer topology

- Operational worktree: `/Users/crm/Documents/GitHub/Investment-Intelligence-OS-batch9i-shadow-counterfactual`
- Inspected commit: `62325804920773424627b9476570fc776a5f270c`
- Natural producer: `scripts/iios_shadow_counterfactual_lab.py`
- Existing schedule: the existing `com.iios.shadow-counterfactual` LaunchAgent invokes that producer every 1,800 seconds. The producer itself admits automatic work only after 16:20 America/New_York on market weekdays.
- Private output: `${state_dir}/shadow_strategy/latest_shadow_counterfactual.json`
- Proposed browser output: `${state_dir}/browser/shadow_strategy.json`

The Expansion Wing branch does not contain the compatible 9I producer or its `BACK END/backend/shadow_counterfactual.py` engine. This batch therefore supplies a pure projection library and tests without copying, activating, or changing the operational worker.

## Durable natural-cycle integration

During a separately reviewed operational rollout, import `build_or_unavailable`, `private_artifact_hash`, and `publish_projection` into the existing producer. Immediately after constructing `local`, compute its opaque hash in memory, atomically write the existing private artifact, construct an exact `SOURCE_FIELDS` input from the already resident aggregate values, and atomically publish the compact projection to `browser/shadow_strategy.json`.

The reviewed producer hook is:

```python
private_hash = private_artifact_hash(local)
_atomic_write(latest_path, local)
browser_source = {
    "generated_at": rollup["generated_at"],
    "status": rollup["status"],
    "complete_session_count": rollup["complete_session_count"],
    "minimum_complete_sessions_for_advice": rollup["minimum_complete_sessions_for_advice"],
    "latest_session_id": latest_session_id,
    "session_ids": rollup["session_ids"],
    "advice_issued": bool(rollup["recommendations"]),
    "five_session_mature_count": max(0, int(rollup["complete_session_count"]) - 4),
    "safety": {
        "ledger_mode": "READ_ONLY",
        "auto_apply_threshold_changes": False,
        "automatic_agent_weight_changes": False,
        "auto_write_judgment_bank": False,
        "trade_execution_permission": False,
        "broker_connected": False,
        "live_execution": False,
    },
}
browser = build_or_unavailable(
    browser_source,
    private_hash,
    generated_at=rollup["generated_at"],
)
publish_projection(state_dir / "browser" / "shadow_strategy.json", browser)
```

The allowlisted source object is limited to generated time, aggregate status, aggregate session counts, latest session ID, bounded session IDs used only for consistency validation, an advice-present boolean, aggregate five-session maturity count, and fixed safety values. It must not pass `session_results`, recommendations, instruments, paths, errors, prompts, evidence, URLs, credentials, or ledger content to the projection builder.

This hook executes once per successful natural 9I completion. It does not add a scheduler, daemon, polling loop, provider, network call, or frontend read of the private artifact. Skip paths before a completed aggregation do not publish a misleading healthy projection.

## Browser schema and safety

Schema `batch9i-browser-shadow-strategy-v1` has exactly these top-level fields:

```text
schema_version generated_at source_session source_artifact_hash status truth_state
complete_sessions required_sessions maturity_state five_session_mature_count advice_issued
observational_only automatic_threshold_changes automatic_weight_changes judgment_bank_auto_write
ledger_read ledger_write trade_execution_permission broker_connected live_execution reason
```

All strings, integers, booleans, hashes, timestamps, statuses, truth states, maturity states, and reasons are bounded and validated. Unknown source or output keys fail closed. Unsafe authority values fail closed. Serialization is deterministic. Publication uses a same-directory temporary file, `fsync`, atomic replacement, and mode 0600; a newly created browser directory is mode 0700.

On malformed source data, missing fields, session mismatch, or unsafe authority, the producer publishes only a fixed-category `UNAVAILABLE` projection. The exception text is constant and contains no source value. Stale data projects as `STALE`, never healthy. Freshness is 86,400 seconds because 9I is a post-session observational aggregate.

## Rollout

1. Checkpoint this projection batch on the Expansion Wing feature branch.
2. Create a dedicated 9I integration branch from the exact operational 9I commit.
3. Cherry-pick or copy only the reviewed projection module and its tests.
4. Add the natural-cycle hook described above to `scripts/iios_shadow_counterfactual_lab.py` after the private atomic write.
5. Run all 9I and projection tests against synthetic fixtures in an isolated directory.
6. Perform one forced fixture-only producer run with a temporary `state_dir`; inspect schema, mode 0600, deterministic hash, and absence of forbidden fields.
7. Review the exact operational diff and separately authorize rollout. Activation is not part of this batch.

## Rollback

Revert only the producer hook and projection-module commit on the dedicated 9I integration branch. On an authorized rollout, remove only the reviewed browser artifact after stopping or naturally quiescing the affected cycle. Do not alter the private artifact, 9H reports, ledger, LaunchAgent schedule, or other browser summaries. A missing browser projection must display `UNAVAILABLE` in Expansion Wing.
