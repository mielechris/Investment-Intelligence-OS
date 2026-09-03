# Batch 9I browser-safe shadow summary

This branch is based on operational Batch 9I commit `62325804920773424627b9476570fc776a5f270c`. It prepares, but does not activate, a browser-safe emission in the existing natural 9I cycle.

## Lifecycle

`scripts/iios_shadow_counterfactual_lab.py` continues to build per-session shadow results and the aggregate private payload exactly as before. It writes `${state_dir}/shadow_strategy/latest_shadow_counterfactual.json` using the unchanged `_atomic_write` function and unchanged deterministic JSON representation. Only after that write succeeds does `_emit_browser_projection` select aggregate scalar fields and publish `${state_dir}/browser/shadow_strategy.json`.

The projection function receives no `session_results`, recommendations, security symbols, trades, source descriptors, paths, URLs, prompts, model responses, raw errors, credentials, headers, or ledger contents. The private payload is supplied only to the byte-compatible SHA-256 helper; it is not parsed or copied into the projection.

The browser artifact implements exactly `batch9i-browser-shadow-strategy-v1`. Its freshness window is 86,400 seconds. Warmup is `INCOMPLETE`; stale is `STALE`; sanitization or authority failure is `UNAVAILABLE`. Publication uses a same-directory temporary file, `fsync`, atomic replacement, a mode-0700 browser directory, and a mode-0600 artifact.

Projection rejection produces only a fixed sanitized unavailable contract. An output filesystem failure is reduced to the fixed producer status `UNAVAILABLE`; the successfully written private artifact is retained. No private values, source-session values, aggregate counts, paths, or exception details are added to process output.

No scheduler, service, process, provider, or authority change is introduced. The existing 1,800-second natural cycle and post-16:20 America/New_York gate remain unchanged.

## Rollout

1. Review and checkpoint only the projection module, its tests, the producer hook, and this document.
2. Rebase or cherry-pick the reviewed commit onto the exact operational 9I lineage.
3. Run the existing 9I, relevant 9H/9J compatibility, and browser-projection tests.
4. Run one synthetic fixture invocation with a mode-0700 temporary state directory.
5. Confirm the operational 9I worktree is clean and separately authorize updating it.
6. Allow the next natural 9I completion to create the browser artifact; do not add or restart a scheduler.

## Rollback

Revert the single reviewed integration commit. After a separately authorized operational quiescence, remove only `${state_dir}/browser/shadow_strategy.json`. Do not alter the private 9I artifact, per-session outputs, ledger, 9H/9J artifacts, LaunchAgent, cadence, or execution authority. Consumers must treat a missing browser artifact as `UNAVAILABLE`.
