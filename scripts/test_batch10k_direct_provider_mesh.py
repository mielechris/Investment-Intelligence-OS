#!/usr/bin/env python3
from __future__ import annotations

from datetime import date

import iios_historical_macro_regime_runtime as runtime


def main() -> int:
    xml = '''<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
      <entry><content type="application/xml"><m:properties>
        <d:NEW_DATE>2026-08-27T00:00:00</d:NEW_DATE><d:BC_2YEAR>3.90</d:BC_2YEAR><d:BC_10YEAR>4.25</d:BC_10YEAR>
      </m:properties></content></entry>
      <entry><content type="application/xml"><m:properties>
        <d:NEW_DATE>2026-08-28T00:00:00</d:NEW_DATE><d:BC_2YEAR>3.88</d:BC_2YEAR><d:BC_10YEAR>4.23</d:BC_10YEAR>
      </m:properties></content></entry>
    </feed>'''
    two, ten = runtime._parse_treasury_xml(xml)
    assert len(two) == 2 and len(ten) == 2
    assert two[-1]["value"] == 3.88 and ten[-1]["value"] == 4.23

    vix = runtime._parse_vix_csv("DATE,OPEN,HIGH,LOW,CLOSE\n08/27/2026,14,15,13,14.5\n08/28/2026,14,15,13,14.3\n")
    assert len(vix) == 2 and vix[-1]["value"] == 14.3

    series = {"UST2Y": two, "UST10Y": ten, "VIX": vix}
    snap = runtime._snapshot(date(2026, 8, 28), series)
    assert snap["tier_a_dimensions_ready"] == 4
    assert snap["tier_a_backtest_eligible"]["curve_10y2y_pct"]["value"] == 0.35

    study = {
        "symbol": "SPY",
        "label": "SPDR S&P 500 ETF",
        "as_of_date": "2026-08-28",
        "status": "ANALOG_STUDY_READY",
        "analogs": [{"date": "2026-08-27", "similarity_score": 91.0, "forward_returns": {"fwd_5d_pct": 1.2}}],
    }
    normalized = runtime._normalize_study(study, series)
    assert normalized["status"] == "MACRO_NORMALIZED_ANALOGS_READY"
    assert normalized["candidate_count"] == 1
    assert normalized["normalization_method"] == "DIRECT_TREASURY_RATE_LEVEL_CURVE_AND_CBOE_VIX_NO_FUTURE_OBSERVATIONS"

    assert runtime.TREASURY_START_YEAR == 1990
    print("BATCH10K_DIRECT_PROVIDER_MESH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
