import json
from pathlib import Path

from intelligence.risk_review import RiskReviewStore


def test_committee_result_enqueues_one_risk_review(tmp_path: Path):
    store = RiskReviewStore(tmp_path / "risk.db")
    escalation = {
        "escalation_id": "esc-1",
        "packet_payload": json.dumps({"evidence": {"title": "IPO filing"}}),
    }
    committee_result = {
        "headline": "Watch pending final terms",
        "disposition": "WATCH",
        "risk_review_required": True,
        "confidence": 0.9,
    }

    assert store.maybe_enqueue(escalation_row=escalation, committee_result=committee_result) is True
    assert store.maybe_enqueue(escalation_row=escalation, committee_result=committee_result) is False
    assert store.counts()["pending"] == 1
    item = store.recent(limit=1)[0]
    assert item["packet"]["committee_result"]["disposition"] == "WATCH"
    assert item["risk_result"] is None


def test_no_risk_review_when_committee_does_not_request_it(tmp_path: Path):
    store = RiskReviewStore(tmp_path / "risk.db")
    escalation = {"escalation_id": "esc-2", "packet_payload": json.dumps({})}
    result = {"risk_review_required": False}
    assert store.maybe_enqueue(escalation_row=escalation, committee_result=result) is False
    assert store.counts()["pending"] == 0
