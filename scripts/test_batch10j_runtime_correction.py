#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
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
    assert [row["date"] for row in selected] == ["2020-03-16", "2022-06-13", "2024-08-05", "2011-01-03"]
    assert meta["inside_doc_corpus"] == 3
    assert meta["outside_doc_corpus"] == 2

    today = datetime.now(timezone.utc).date()
    url = runtime._bounded_gdelt_url("SPY", "SPDR S&P 500 ETF", today, 2)
    query = parse_qs(urlparse(url).query)
    end = datetime.strptime(query["enddatetime"][0], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    assert end <= datetime.now(timezone.utc)
    start = datetime.strptime(query["startdatetime"][0], "%Y%m%d%H%M%S").date()
    assert start >= runtime.DOC_SEARCH_START

    # Google News fallback must reject out-of-window RSS items even if the search
    # engine returns them alongside valid historical results.
    rss = """<?xml version='1.0' encoding='UTF-8'?>
    <rss><channel>
      <item><title>Stocks tumble as Fed shocks markets</title><link>https://example.com/a</link><pubDate>Mon, 16 Mar 2020 12:00:00 GMT</pubDate><source>Example A</source></item>
      <item><title>Out of window article</title><link>https://example.com/b</link><pubDate>Mon, 23 Mar 2020 12:00:00 GMT</pubDate><source>Example B</source></item>
    </channel></rss>"""
    start_dt = datetime(2020, 3, 14, tzinfo=timezone.utc)
    end_dt = datetime(2020, 3, 18, 23, 59, 59, tzinfo=timezone.utc)
    rows = runtime._normalize_google_rss(rss, start_dt, end_dt)
    assert len(rows) == 1
    assert rows[0]["provider"] == "GOOGLE_NEWS_RSS"
    assert rows[0]["title"].startswith("Stocks tumble")

    # Provider mesh: simulate GDELT failure and Google News success. The runtime
    # must use the date-verified fallback without disabling TLS or inventing rows.
    original_curl = runtime._system_curl_text
    try:
        def fake_curl(target: str) -> str:
            if "api.gdeltproject.org" in target:
                raise RuntimeError("simulated GDELT timeout")
            if "news.google.com" in target:
                return rss
            raise AssertionError(target)

        runtime._system_curl_text = fake_curl
        with tempfile.TemporaryDirectory() as tmp:
            articles, provider = runtime._fetch_articles_mesh(
                symbol="SPY",
                label="SPDR S&P 500 ETF",
                center=date(2020, 3, 16),
                event_dir=Path(tmp),
                span_days=2,
                current=False,
            )
        assert len(articles) == 1
        assert provider["provider"] == "GOOGLE_NEWS_RSS"
        assert provider["provider_mesh"] is True
        assert provider["coverage_contract"] == "RESULT_PUBLISHED_DATE_VERIFIED_PER_WINDOW_NO_GLOBAL_CORPUS_START_CLAIM"
        assert any(row.get("provider") == "GDELT_DOC_2" and row.get("status") == "PROVIDER_ERROR" for row in provider["attempts"])
    finally:
        runtime._system_curl_text = original_curl

    print("BATCH10J_RUNTIME_CORRECTION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
