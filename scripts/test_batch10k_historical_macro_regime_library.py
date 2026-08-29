#!/usr/bin/env python3
from __future__ import annotations

from datetime import date, timedelta

import iios_historical_macro_regime_library as macro


def series(start: str, values: list[float], step_days: int = 1):
    day = date.fromisoformat(start)
    return [{"date": (day + timedelta(days=index * step_days)).isoformat(), "value": value} for index, value in enumerate(values)]


def main() -> int:
    # Daily market-observable histories around two analogous periods.
    data = {
        "DFF": series("2019-01-01", [2.4] * 2500),
        "DGS2": series("2019-01-01", [2.2] * 2500),
        "DGS10": series("2019-01-01", [2.7] * 2500),
        "VIXCLS": series("2019-01-01", [18.0] * 2500),
        "BAMLH0A0HYM2": series("2019-01-01", [3.5] * 2500),
        "CPIAUCSL": series("2017-01-01", [250 + index * 0.2 for index in range(140)], 30),
        "UNRATE": series("2017-01-01", [4.0] * 140, 30),
        "GDPC1": series("2010-01-01", [18000 + index * 50 for index in range(80)], 91),
        "WALCL": series("2017-01-01", [4000000 + index * 1000 for index in range(500)], 7),
    }
    current = date.fromisoformat("2024-08-28")
    snap = macro.macro_snapshot(current, data)
    assert snap["tier_a_dimensions_ready"] == 4
    assert snap["tier_b_dimensions_ready"] >= 2
    # Tier B is never allowed into formal macro-distance scoring.
    assert snap["point_in_time_policy"]["tier_b"] == "CONTEXT_ONLY_CURRENT_HISTORY_NOT_REVISION_VINTAGE_SAFE"

    study = {
        "symbol": "SPY",
        "label": "SPDR S&P 500 ETF",
        "status": "ANALOG_STUDY_READY",
        "as_of_date": current.isoformat(),
        "analogs": [
            {"date": "2024-07-15", "similarity_score": 90.0, "forward_returns": {"fwd_20d_pct": 2.0}},
            {"date": "2022-06-13", "similarity_score": 88.0, "forward_returns": {"fwd_20d_pct": -4.0}},
        ],
    }
    normalized = macro.normalize_study(study, data)
    assert normalized["status"] == "MACRO_NORMALIZED_ANALOGS_READY"
    assert normalized["macro_normalized_analogs"]
    assert normalized["tier_b_usage"] == "CONTEXT_ONLY_NOT_USED_IN_ANALOG_RANKING"

    payload = macro.build_library(
        historical={"studies": [study]},
        series_data=data,
        provider_meta={key: {"provider": "FRED", "error": None} for key in macro.SERIES},
    )
    assert payload["status"] == "HISTORICAL_MACRO_REGIME_LIBRARY_ACTIVE"
    assert payload["coverage"]["normalized_symbols_ready"] == 1
    assert payload["coverage"]["tier_a_series_ready"] == 5
    safety = payload["safety"]
    for key in (
        "auto_generate_trades",
        "auto_change_thresholds",
        "auto_change_agent_weights",
        "auto_change_model_routing",
        "auto_change_portfolio_exposure",
        "provider_change_authority",
        "broker_connection_authority",
        "capital_authority",
        "trade_execution_permission",
        "live_execution",
    ):
        assert safety[key] is False, key
    print("BATCH10K_HISTORICAL_MACRO_REGIME_LIBRARY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
