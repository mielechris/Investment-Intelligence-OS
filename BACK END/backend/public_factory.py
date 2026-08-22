from __future__ import annotations

from typing import Any

from main import TopicRequest, run_factory
from source_ingestion import SOURCE_REGISTRY, ingest_sources


def run_public_factory(topic: str, source_requests: list[dict[str, Any]]) -> dict[str, Any]:
    """Fetch public evidence, then run the existing governed factory on the collected packet."""
    ingestion = ingest_sources(source_requests)
    factory = run_factory(
        TopicRequest(
            topic=topic,
            evidence=ingestion["evidence_items"],
        )
    )
    return {
        "topic": topic,
        "source_registry": SOURCE_REGISTRY,
        "ingestion": ingestion,
        "factory": factory,
    }
