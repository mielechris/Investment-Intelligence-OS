#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import iios_daily_factory_episode as core

FULL_LEARNING_FILENAME = "latest_outcome_learning.json"
COMPACT_LEARNING_RELATIVE = Path("browser") / "outcome_learning.json"


def _learning_state(state_dir: Path) -> tuple[dict, str, Path]:
    full_path = state_dir / FULL_LEARNING_FILENAME
    compact_path = state_dir / COMPACT_LEARNING_RELATIVE
    full = core._read_json(full_path)
    if isinstance(full, dict):
        return full, "CASE_AND_CANDIDATE_LINKED", full_path
    compact = core._read_json(compact_path)
    if isinstance(compact, dict):
        return compact, "COMPACT_BROWSER_FALLBACK", compact_path
    return {}, "WAITING", full_path


def build_from_state(
    *,
    state_dir: Path = core.DEFAULT_STATE_DIR,
    telemetry_dir: Path = core.DEFAULT_TELEMETRY_DIR,
    generated_at: datetime | None = None,
    final_requested: bool = False,
) -> dict:
    scorecard = core._read_json(state_dir / "latest_market_validation.json") or {}
    shadow = core._read_json(
        state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json"
    ) or {}
    learning, lineage_mode, learning_path = _learning_state(state_dir)
    telemetry = core._read_json(telemetry_dir / "latest.json") or {}

    if not scorecard and not telemetry:
        return {
            "schema_version": core.SCHEMA_VERSION,
            "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
            "status": "WAITING_FOR_PERSISTED_FACTORY_STATE",
            "episode_session_id": None,
            "source_freshness": {
                "learning_lineage_mode": lineage_mode,
                "learning_source_filename": learning_path.name,
            },
            "safety": {
                "report_only": True,
                "source_mode": "PERSISTED_9G_9H_9I_9J_EXACT_LINKED_READ_ONLY",
                "direct_ledger_access": False,
                "trade_execution_permission": False,
                "live_execution": False,
            },
        }

    payload = core.build_daily_episode(
        scorecard=scorecard,
        shadow=shadow,
        learning=learning,
        telemetry=telemetry,
        generated_at=generated_at,
        final_requested=final_requested,
    )
    freshness = payload.setdefault("source_freshness", {})
    freshness["learning_lineage_mode"] = lineage_mode
    freshness["learning_source_filename"] = learning_path.name
    safety = payload.setdefault("safety", {})
    safety["source_mode"] = (
        "PERSISTED_9G_9H_9I_9J_EXACT_LINKED_READ_ONLY"
        if lineage_mode == "CASE_AND_CANDIDATE_LINKED"
        else "PERSISTED_9G_9H_9I_9J_COMPACT_FALLBACK_READ_ONLY"
    )

    # A compact fallback may summarize a session, but it is not allowed to be
    # represented as the same lineage quality as the full exact-linked 9J file.
    if final_requested and lineage_mode != "CASE_AND_CANDIDATE_LINKED":
        payload["status"] = "FINAL_WITH_LEARNING_WARMUP"
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Batch 9O daily episode from persisted exact-linked IIOS state."
    )
    parser.add_argument("--state-dir", default=str(core.DEFAULT_STATE_DIR))
    parser.add_argument("--telemetry-dir", default=str(core.DEFAULT_TELEMETRY_DIR))
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Build a read-only LIVE_DRAFT and do not write final episode JSON",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow final generation before the normal 16:45 ET window",
    )
    parser.add_argument("--stdout", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser()
    telemetry_dir = Path(args.telemetry_dir).expanduser()
    now_ny = datetime.now(core.NEW_YORK)
    output_path = state_dir / "browser" / "daily_factory_episode.json"

    if args.preview:
        payload = build_from_state(
            state_dir=state_dir,
            telemetry_dir=telemetry_dir,
            generated_at=now_ny.astimezone(timezone.utc),
            final_requested=False,
        )
        print(
            json.dumps(
                payload,
                indent=2 if args.stdout else None,
                sort_keys=True,
                default=str,
            )
        )
        return 0

    if not args.force:
        if now_ny.weekday() >= 5:
            print(
                json.dumps(
                    {"status": "SKIPPED_NON_MARKET_DAY", "as_of": now_ny.isoformat()}
                )
            )
            return 0
        if now_ny.time().replace(tzinfo=None) < core.FINAL_WINDOW:
            print(
                json.dumps(
                    {
                        "status": "SKIPPED_BEFORE_EPISODE_WINDOW",
                        "as_of": now_ny.isoformat(),
                    }
                )
            )
            return 0

    payload = build_from_state(
        state_dir=state_dir,
        telemetry_dir=telemetry_dir,
        generated_at=now_ny.astimezone(timezone.utc),
        final_requested=True,
    )
    if payload.get("status") == "WAITING_FOR_PERSISTED_FACTORY_STATE":
        print(json.dumps(payload, sort_keys=True))
        return 0

    previous = core._read_json(output_path)
    if (
        previous
        and previous.get("episode_session_id") == payload.get("episode_session_id")
        and previous.get("status") == "FINAL"
        and payload.get("status") == "FINAL"
        and not args.force
    ):
        print(
            json.dumps(
                {
                    "status": "SKIPPED_EPISODE_ALREADY_FINAL",
                    "episode_session_id": payload.get("episode_session_id"),
                }
            )
        )
        return 0

    core._atomic_write(output_path, payload)
    summary = {
        "status": "BATCH9O_DAILY_FACTORY_EPISODE_WRITTEN",
        "episode_status": payload.get("status"),
        "episode_session_id": payload.get("episode_session_id"),
        "learning_lineage_mode": (payload.get("source_freshness") or {}).get(
            "learning_lineage_mode"
        ),
        "output": str(output_path),
        "best_call_count": len(payload.get("best_calls") or []),
        "save_count": len(payload.get("saves") or []),
        "dumb_call_count": len(payload.get("dumb_calls") or []),
        "validation_miss_count": len(payload.get("misses") or []),
        "direct_ledger_access": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }
    print(
        json.dumps(
            payload if args.stdout else summary,
            indent=2 if args.stdout else None,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
