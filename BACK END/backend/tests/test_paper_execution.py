import json

from intelligence.paper_execution import PaperExecutionStore


def _risk_row():
    return {
        "risk_review_id": "risk-1",
        "packet_payload": json.dumps({"committee_result": {"headline": "test"}}),
    }


def test_veto_never_creates_paper_candidate(tmp_path):
    store = PaperExecutionStore(tmp_path / "paper.db")
    created = store.maybe_enqueue(
        risk_row=_risk_row(),
        risk_result={
            "decision": "VETOED",
            "paper_execution_eligible": True,
            "hard_vetoes": [],
        },
    )
    assert created is False
    assert store.counts()["ready"] == 0


def test_watch_only_eligible_candidate_is_deduplicated(tmp_path):
    store = PaperExecutionStore(tmp_path / "paper.db")
    result = {
        "decision": "WATCH_ONLY",
        "risk_level": "MEDIUM",
        "headline": "bounded paper test",
        "paper_execution_eligible": True,
        "hard_vetoes": [],
    }
    assert store.maybe_enqueue(risk_row=_risk_row(), risk_result=result) is True
    assert store.maybe_enqueue(risk_row=_risk_row(), risk_result=result) is False
    assert store.counts()["ready"] == 1


def test_simulation_never_uses_real_capital(tmp_path, monkeypatch):
    monkeypatch.setenv("IIOS_MAX_PAPER_NOTIONAL", "25000")
    store = PaperExecutionStore(tmp_path / "paper.db")
    result = {
        "decision": "WATCH_ONLY",
        "risk_level": "MEDIUM",
        "headline": "bounded paper test",
        "paper_execution_eligible": True,
        "hard_vetoes": [],
    }
    store.maybe_enqueue(risk_row=_risk_row(), risk_result=result)
    candidate = store.recent(limit=1)[0]
    order = store.simulate(candidate["candidate_id"])
    assert order["simulated_notional"] == 25000
    assert order["real_notional"] == 0
    assert order["broker_order_sent"] is False
    assert order["live_execution"] is False


def test_controlled_fixture_is_synthetic_deduplicated_and_zero_real_capital(tmp_path):
    store = PaperExecutionStore(tmp_path / "paper.db")
    first = store.create_controlled_test_candidate()
    second = store.create_controlled_test_candidate()

    assert first["created"] is True
    assert second["created"] is False
    assert store.counts()["ready"] == 1

    candidate = first["candidate"]
    assert candidate is not None
    assert candidate["packet"]["risk_result"]["synthetic_fixture"] is True

    order = store.simulate(candidate["candidate_id"])
    assert order["synthetic_fixture"] is True
    assert order["real_notional"] == 0
    assert order["broker_order_sent"] is False
    assert order["live_execution"] is False
