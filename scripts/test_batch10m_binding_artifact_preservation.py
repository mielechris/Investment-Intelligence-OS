#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import iios_model_cost_governor as governor


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        cost_dir = Path(tmp) / "model-cost"
        now = datetime(2026, 8, 29, 16, 30, tzinfo=timezone.utc)

        advisory = governor.build_governor(cost_dir, now=now)
        assert advisory["status"] == "MODEL_COST_GOVERNOR_INSTRUMENTATION_REQUIRED"
        assert advisory["enforcement_hooks_connected"] is False

        write_json(cost_dir / "enforcement_hooks.json", {
            "hooks": {
                "xai_grok_social_intelligence": {
                    "connected": True,
                    "binding": True,
                    "pre_call_admission": True,
                    "post_call_exact_cost": True,
                }
            }
        })

        binding = governor.build_governor(cost_dir, now=now)
        assert binding["status"] == "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE"
        assert binding["budget_state"] == "INSTRUMENTATION_BOOTSTRAP"
        assert binding["enforcement_hooks_connected"] is True
        assert binding["binding_xai_grok_hook"] is True
        assert binding["rolling_7d"]["exact_spend_usd"] is None
        assert binding["safety"]["capital_authority"] is False
        assert binding["safety"]["trade_execution_permission"] is False
        assert binding["safety"]["live_execution"] is False

        governor.record_usage(cost_dir, {
            "timestamp": "2026-08-29T16:20:00+00:00",
            "provider": "XAI",
            "model": "grok-4.6",
            "task_type": "GROK_X_SEARCH",
            "case_id": "CASE-TEST",
            "agent": "GROK_SOCIAL_INTELLIGENCE",
            "input_tokens": 1000,
            "cached_input_tokens": 600,
            "output_tokens": 150,
            "x_search_calls": 2,
            "cost_usd": 1.25,
            "cost_source": "XAI_COST_IN_USD_TICKS",
            "query": "test catalyst",
        })
        measured = governor.build_governor(cost_dir, now=now)
        assert measured["status"] == "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE"
        assert measured["budget_state"] == "WITHIN_BUDGET"
        assert measured["rolling_7d"]["exact_spend_usd"] == 1.25
        assert measured["rolling_7d"]["x_search_calls"] == 2
        assert measured["rolling_7d"]["exact_cost_coverage_pct"] == 100.0
        assert measured["enforcement_hooks_connected"] is True

    print("BATCH10M_BINDING_ARTIFACT_PRESERVATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
