from intelligence.postmortem_intelligence import PostmortemIntelligenceStore


def _review():
    return {
        "position_id": "position-1",
        "symbol": "IIOS-TEST",
        "side": "LONG",
        "outcome": "WIN",
        "return_pct": 5.0,
        "realized_pnl": 500.0,
        "synthetic_fixture": True,
    }


def _result():
    return {
        "headline": "Synthetic workflow validated without real-market inference",
        "thesis_assessment": "INSUFFICIENT_EVIDENCE",
        "outcome_interpretation": "The fixture validates process plumbing only.",
        "what_worked": ["Risk-to-paper-to-ledger handoff completed."],
        "what_failed": [],
        "signals_that_mattered": [],
        "risks_overstated": [],
        "risks_understated": [],
        "causal_unknowns": ["No real market cause exists in a synthetic fixture."],
        "hindsight_traps": ["Do not treat a synthetic win as investment skill."],
        "regime_tags": ["PROCESS_VALIDATION"],
        "reusable_patterns": ["Use deterministic fixtures to validate state transitions."],
        "anti_patterns": ["Do not infer market alpha from synthetic P&L."],
        "next_time_rules": ["Keep synthetic and real outcomes visibly separated."],
        "confidence": 1.0,
        "synthetic_fixture": True,
    }


def test_postmortem_queue_deduplicates_review(tmp_path):
    store = PostmortemIntelligenceStore(tmp_path / "postmortems.db")
    assert store.maybe_enqueue(review_id="review-1", review=_review()) is True
    assert store.maybe_enqueue(review_id="review-1", review=_review()) is False
    assert store.counts()["pending"] == 1


def test_pattern_library_is_searchable(tmp_path):
    store = PostmortemIntelligenceStore(tmp_path / "postmortems.db")
    store._save_pattern(review_id="review-1", review=_review(), result=_result())
    matches = store.search_patterns("PROCESS_VALIDATION")
    assert len(matches) == 1
    assert matches[0]["symbol"] == "IIOS-TEST"
    assert matches[0]["synthetic_fixture"] is True
    assert "SYNTHETIC_FIXTURE" in matches[0]["tags"]
    assert matches[0]["lesson"]["next_time_rules"][0].startswith("Keep synthetic")
