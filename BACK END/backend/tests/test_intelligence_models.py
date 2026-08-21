from datetime import datetime, timezone

from intelligence.models import EvidenceItem, EvidencePacket, TradeThesis


def test_evidence_packet_counts_fresh_sources():
    packet = EvidencePacket(
        topic="rates and technology stocks",
        items=[
            EvidenceItem(
                source_name="Example Macro Source",
                source_kind="macro",
                title="Rates update",
                summary="Example evidence",
                freshness="fresh",
                observed_at=datetime.now(timezone.utc),
            ),
            EvidenceItem(
                source_name="Example Policy Source",
                source_kind="policy",
                title="Policy update",
                summary="Example evidence",
                freshness="stale",
                observed_at=datetime.now(timezone.utc),
            ),
        ],
    )

    assert packet.source_count == 2
    assert packet.fresh_source_count == 1


def test_trade_thesis_defaults_to_paper_mode():
    thesis = TradeThesis(
        topic="semiconductors",
        asset="SOXX",
        direction="WATCH",
        thesis="Monitor the thesis until fresh evidence is available.",
    )

    assert thesis.paper_mode is True
