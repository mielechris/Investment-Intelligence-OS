#!/usr/bin/env python3
from __future__ import annotations

from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

import iios_historical_event_reconstruction_runtime as runtime


def main() -> int:
    assert runtime.DOC_SEARCH_START == date(2017, 1, 1)

    study = {
        "analogs": [
            {"date": "2011-01-03", "similarity_score": 99},
            {"date": "2020-03-16", "similarity_score": 98},
            {"date": "2013-06-01", "similarity_score": 97},
            {"date": "2022-06-13", "similarity_score": 96},
            {"date": "2024-08-05", "similarity_score": 95},
        ]
    }
    selected, meta = runtime._eligible_event_analogs(study)
    assert [row["date"] for row in selected] == ["2020-03-16", "2022-06-13", "2024-08-05"]
    assert meta["inside_doc_corpus"] == 3
    assert meta["outside_doc_corpus"] == 2

    today = datetime.now(timezone.utc).date()
    url = runtime._bounded_gdelt_url("SPY", "SPDR S&P 500 ETF", today, 2)
    query = parse_qs(urlparse(url).query)
    end = datetime.strptime(query["enddatetime"][0], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    assert end <= datetime.now(timezone.utc)
    start = datetime.strptime(query["startdatetime"][0], "%Y%m%d%H%M%S").date()
    assert start >= runtime.DOC_SEARCH_START

    print("BATCH10J_RUNTIME_CORRECTION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
