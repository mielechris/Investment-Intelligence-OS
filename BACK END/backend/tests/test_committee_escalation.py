import json
from pathlib import Path

from intelligence.committee_escalation import CommitteeEscalationStore


def _dispatch_row(dispatch_id: str = "dispatch-1", *, synthetic: bool = False) -> dict:
    evidence = {
        "source_name": "Federal Reserve Bank of St. Louis FRED",
        "source_kind": "macro",
        "title": "DGS10 latest observation",
        "summary": "DGS10 = 4.1 for observation date 2026-08-20.",
    }
    if synthetic:
        evidence = {
            "source_name": "IIOS Synthetic Test",
            "source_kind": "market",
            "title": "Synthetic controlled paper handoff",
            "summary": "Synthetic fixture process validation with zero real capital.",
            "synthetic_fixture": True,
        }
    return {
        "dispatch_id": dispatch_id,
        "agent_id": "system-market-history-regime-agent",
        "route_reason": "macro evidence can inform regime history",
        "evidence_payload": json.dumps(evidence),
    }


def test_high_materiality_high_confidence_escalates(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IIOS_COMMITTEE_CONFIDENCE_THRESHOLD", "0.70")
    store = CommitteeEscalationStore(tmp_path / "committee.db")

    created = store.maybe_enqueue(
        dispatch_row=_dispatch_row(),
        result={
            "materiality": "HIGH",
            "confidence": 0.82,
            "committee_escalation": True,
            "headline": "Rates regime shifted",
            "disposition": "WATCH",
        },
    )

    assert created is True
    assert store.counts()["pending"] == 1


def test_synthetic_high_confidence_event_never_escalates(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IIOS_COMMITTEE_CONFIDENCE_THRESHOLD", "0.70")
    store = CommitteeEscalationStore(tmp_path / "committee.db")

    created = store.maybe_enqueue(
        dispatch_row=_dispatch_row(synthetic=True),
        result={
            "materiality": "HIGH",
            "confidence": 0.99,
            "committee_escalation": True,
            "headline": "Synthetic workflow test",
            "disposition": "NO_TRADE",
        },
    )

    assert created is False
    assert store.counts()["pending"] == 0


def test_medium_materiality_does_not_escalate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IIOS_COMMITTEE_CONFIDENCE_THRESHOLD", "0.70")
    store = CommitteeEscalationStore(tmp_path / "committee.db")

    created = store.maybe_enqueue(
        dispatch_row=_dispatch_row(),
        result={
            "materiality": "MEDIUM",
            "confidence": 0.95,
            "committee_escalation": True,
        },
    )

    assert created is False
    assert store.counts()["pending"] == 0


def test_low_confidence_high_materiality_does_not_escalate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IIOS_COMMITTEE_CONFIDENCE_THRESHOLD", "0.75")
    store = CommitteeEscalationStore(tmp_path / "committee.db")

    created = store.maybe_enqueue(
        dispatch_row=_dispatch_row(),
        result={
            "materiality": "HIGH",
            "confidence": 0.60,
            "committee_escalation": True,
        },
    )

    assert created is False
    assert store.counts()["pending"] == 0


def test_same_dispatch_only_escalates_once(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IIOS_COMMITTEE_CONFIDENCE_THRESHOLD", "0.70")
    store = CommitteeEscalationStore(tmp_path / "committee.db")
    result = {
        "materiality": "HIGH",
        "confidence": 0.88,
        "committee_escalation": True,
    }

    assert store.maybe_enqueue(dispatch_row=_dispatch_row(), result=result) is True
    assert store.maybe_enqueue(dispatch_row=_dispatch_row(), result=result) is False
    assert store.counts()["pending"] == 1
