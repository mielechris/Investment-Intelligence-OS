#!/usr/bin/env python3
from __future__ import annotations

from iios_final_institutional_publisher import _apply_macro_feedback


def main() -> int:
    office = {
        "whole_stack_inputs": [{"layer": "10J", "status": "HISTORICAL_EVENT_RECONSTRUCTION_ACTIVE"}],
        "whole_stack_input_count": 1,
        "whole_stack_inputs_observed": 1,
        "ranked_upgrades": [
            {"upgrade_id": "HISTORICAL_REGIME_LIBRARY", "priority_score": 112},
            {"upgrade_id": "BENCHMARK_ALPHA_ATTRIBUTION", "priority_score": 110},
            {"upgrade_id": "DATA_HEALTH_WATCHDOG", "priority_score": 108},
        ],
        "top_recommendation": {"upgrade_id": "HISTORICAL_REGIME_LIBRARY", "priority_score": 112},
        "historical_diagnostics": {"regime_normalization_state": "PARTIAL"},
    }
    warm = _apply_macro_feedback(office, {"status": "HISTORICAL_MACRO_REGIME_LIBRARY_WARM_UP", "coverage": {"normalized_symbols_ready": 0}})
    assert warm["top_recommendation"]["upgrade_id"] == "HISTORICAL_REGIME_LIBRARY"
    active = _apply_macro_feedback(office, {"status": "HISTORICAL_MACRO_REGIME_LIBRARY_ACTIVE", "coverage": {"normalized_symbols_ready": 4, "tier_a_series_ready": 5, "tier_b_context_series_ready": 4}})
    assert active["top_recommendation"]["upgrade_id"] == "BENCHMARK_ALPHA_ATTRIBUTION"
    assert all(row["upgrade_id"] != "HISTORICAL_REGIME_LIBRARY" for row in active["ranked_upgrades"])
    assert active["historical_diagnostics"]["regime_normalization_state"] == "ACTIVE"
    assert active["whole_stack_inputs"][-1]["layer"] == "10K"
    print("BATCH10K_10I_FEEDBACK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
