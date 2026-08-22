from datetime import datetime, timezone
from pathlib import Path

from intelligence.evidence_store import EvidenceStore
from intelligence.models import EvidenceItem


def test_evidence_store_deduplicates_and_reopens(tmp_path: Path):
    database_path = tmp_path / "iios.db"
    store = EvidenceStore(database_path=database_path)
    item = EvidenceItem(
        source_name="SEC EDGAR",
        source_kind="company",
        title="Example S-1 filing",
        url="https://www.sec.gov/example",
        published_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        summary="Example IPO registration statement.",
        freshness="fresh",
        confidence=0.99,
    )

    assert store.save(item) is True
    assert store.save(item) is False
    assert store.count() == 1

    reopened = EvidenceStore(database_path=database_path)
    recent = reopened.recent(limit=10)
    assert len(recent) == 1
    assert recent[0].title == item.title


def test_evidence_store_filters_by_source_kind(tmp_path: Path):
    store = EvidenceStore(database_path=tmp_path / "iios.db")
    store.save(
        EvidenceItem(
            source_name="FRED",
            source_kind="macro",
            title="Rates",
            summary="Rates observation.",
        )
    )
    store.save(
        EvidenceItem(
            source_name="CoinGecko",
            source_kind="market",
            title="Bitcoin",
            summary="Bitcoin price observation.",
        )
    )

    macro = store.recent(source_kind="macro")
    assert len(macro) == 1
    assert macro[0].source_kind == "macro"
