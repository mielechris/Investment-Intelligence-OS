#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

import iios_historical_event_reconstruction as event


def _articles(*titles: str):
    return [{"title": title, "url": f"https://example.test/{index}", "domain": "example.test"} for index, title in enumerate(titles)]


def test_classification_is_association_not_causal_claim() -> None:
    context = event.classify_event_context(_articles(
        "Federal Reserve signals interest rate cut after FOMC meeting",
        "Powell says Fed will watch inflation before next rate decision",
        "Wall Street rallies as interest rate expectations shift",
        "Bond yields fall after Federal Reserve comments",
    ))
    assert context["status"] == "EVENT_CONTEXT_READY"
    assert context["candidate_event_type"] == "MONETARY_POLICY_RATES"
    assert context["causal_claim"] is False
    assert context["association_confidence_pct"] > 0


def test_pre_modern_corpus_date_never_invents_event_context() -> None:
    with tempfile.TemporaryDirectory() as temp:
        articles, provider = event._fetch_articles(
            symbol="^SPX",
            label="S&P 500 Index",
            center=event.date(2008, 9, 15),
            event_dir=Path(temp),
        )
    assert articles == []
    assert provider["status"] == "OUTSIDE_MODERN_NEWS_CORPUS_COVERAGE"


def test_reconstruction_matches_event_type_without_future_leakage() -> None:
    original = event._fetch_articles
    try:
        def fake_fetch(*, symbol, label, center, event_dir, span_days=2, current=False):
            if center.isoformat() in {"2026-08-28", "2022-01-03"}:
                rows = _articles(
                    "Federal Reserve signals interest rate change",
                    "Powell comments move bond yields",
                    "Markets react to Fed policy outlook",
                    "Rate expectations shift after FOMC news",
                )
            else:
                rows = _articles(
                    "Oil prices rise after OPEC supply news",
                    "Energy shares gain with crude prices",
                    "OPEC production decision moves oil market",
                )
            return rows, {"provider": "TEST", "status": "OK", "error": None, "cache_hit": False}

        event._fetch_articles = fake_fetch
        study = {
            "symbol": "SPY",
            "label": "SPDR S&P 500 ETF",
            "status": "ANALOG_STUDY_READY",
            "as_of_date": "2026-08-28",
            "method": "FEATURE_DISTANCE_NO_FUTURE_LEAKAGE",
            "analogs": [
                {"date": "2022-01-03", "similarity_score": 88.0, "forward_returns": {"fwd_5d_pct": 2.0, "fwd_20d_pct": 5.0}},
                {"date": "2021-03-01", "similarity_score": 80.0, "forward_returns": {"fwd_5d_pct": -1.0, "fwd_20d_pct": 3.0}},
            ],
        }
        result = event.reconstruct_study(study, Path("/tmp/unused"))
    finally:
        event._fetch_articles = original

    assert result["status"] == "EVENT_RECONSTRUCTION_READY"
    assert result["truth_contract"] == "ASSOCIATED_EVENT_EVIDENCE_NOT_CAUSAL_PROOF"
    assert result["event_match_summary"]["current_event_type"] == "MONETARY_POLICY_RATES"
    assert result["event_match_summary"]["event_matched_analog_count"] == 1
    assert result["event_match_summary"]["event_matched_5d_median_pct"] == 2.0


def test_cycle_is_read_only_and_advisory() -> None:
    original = event._fetch_articles
    try:
        event._fetch_articles = lambda **kwargs: (
            _articles(
                "Federal Reserve policy outlook moves stocks",
                "Interest rate expectations shift after Powell remarks",
                "FOMC news changes bond yields",
            ),
            {"provider": "TEST", "status": "OK", "error": None, "cache_hit": False},
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            historical_dir = root / "historical"
            event_dir = root / "events"
            historical_dir.mkdir()
            event._atomic_write(historical_dir / "latest_historical_market_intelligence.json", {
                "studies": [{
                    "symbol": "SPY",
                    "label": "SPDR S&P 500 ETF",
                    "status": "ANALOG_STUDY_READY",
                    "as_of_date": "2026-08-28",
                    "method": "FEATURE_DISTANCE_NO_FUTURE_LEAKAGE",
                    "analogs": [
                        {"date": "2022-01-03", "similarity_score": 88.0, "forward_returns": {"fwd_5d_pct": 1.5}},
                    ],
                }]
            })
            payload = event.run_cycle(historical_dir=historical_dir, event_dir=event_dir)
    finally:
        event._fetch_articles = original

    assert payload["status"] == "HISTORICAL_EVENT_RECONSTRUCTION_ACTIVE"
    assert payload["research_summary"]["symbols_ready"] == 1
    safety = payload["safety"]
    assert safety["read_only_research"] is True
    assert safety["causal_claim_authority"] is False
    assert safety["auto_generate_trades"] is False
    assert safety["capital_authority"] is False
    assert safety["trade_execution_permission"] is False
    assert safety["live_execution"] is False


if __name__ == "__main__":
    test_classification_is_association_not_causal_claim()
    test_pre_modern_corpus_date_never_invents_event_context()
    test_reconstruction_matches_event_type_without_future_leakage()
    test_cycle_is_read_only_and_advisory()
    print("Batch 10J historical event reconstruction tests: PASS")
