import importlib


outcome_module = importlib.import_module("intelligence.outcome_learning")


class FakeEvidenceStore:
    def __init__(self):
        self.items = []

    def save(self, item):
        self.items.append(item)
        return True


class FakeDispatcher:
    def __init__(self):
        self.items = []

    def enqueue(self, items):
        self.items.extend(items)
        return len(items)


def _closed_position():
    return {
        "position_id": "position-1",
        "symbol": "IIOS-TEST",
        "side": "LONG",
        "quantity": 100.0,
        "entry_price": 100.0,
        "mark_price": 105.0,
        "simulated_notional": 10000.0,
        "unrealized_pnl": 0.0,
        "realized_pnl": 500.0,
        "status": "closed",
        "synthetic_fixture": True,
        "opened_at": "2026-08-21T20:00:00+00:00",
        "closed_at": "2026-08-21T20:15:00+00:00",
        "thesis": {
            "risk_result": {
                "decision": "WATCH_ONLY",
                "risk_level": "LOW",
                "headline": "controlled test",
            },
            "paper_mode": True,
            "real_capital": 0,
        },
    }


def test_closed_position_becomes_history_evidence(tmp_path, monkeypatch):
    fake_evidence = FakeEvidenceStore()
    fake_dispatcher = FakeDispatcher()
    monkeypatch.setattr(outcome_module, "evidence_store", fake_evidence)
    monkeypatch.setattr(outcome_module, "dispatcher", fake_dispatcher)

    store = outcome_module.OutcomeLearningStore(tmp_path / "learning.db")
    result = store.create_from_closed_position(_closed_position())

    assert result["created"] is True
    assert result["review"]["outcome"] == "WIN"
    assert result["review"]["return_pct"] == 5.0
    assert result["history_dispatches"] == 1
    assert len(fake_evidence.items) == 1
    assert fake_evidence.items[0].source_name == "IIOS Outcome Ledger"
    assert fake_evidence.items[0].source_kind == "market"
    assert len(fake_dispatcher.items) == 1


def test_outcome_review_is_deduplicated(tmp_path, monkeypatch):
    fake_evidence = FakeEvidenceStore()
    fake_dispatcher = FakeDispatcher()
    monkeypatch.setattr(outcome_module, "evidence_store", fake_evidence)
    monkeypatch.setattr(outcome_module, "dispatcher", fake_dispatcher)

    store = outcome_module.OutcomeLearningStore(tmp_path / "learning.db")
    first = store.create_from_closed_position(_closed_position())
    second = store.create_from_closed_position(_closed_position())

    assert first["created"] is True
    assert second["created"] is False
    assert len(fake_evidence.items) == 1
    assert len(fake_dispatcher.items) == 1
