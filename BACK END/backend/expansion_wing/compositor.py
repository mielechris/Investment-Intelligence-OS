from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import JsonArtifactAdapter
from .projection import build_living_wall_projection
from .schema_maps import CONTRACTS

SOURCE_SECTION = {"9a": "service_health", "9b": "last_cycle", "9e": "radar", "9h": "benchmark_9h",
                  "9i": "shadow_9i", "9j": "outcomes_9j", "paper_fund": "books"}


def compose_snapshot(paths: dict[str, str | Path | None], *, fixture: bool = False,
                     now: datetime | None = None, max_sources: int = 7) -> dict[str, Any]:
    if len(paths) > max_sources:
        raise ValueError("snapshot source limit exceeded")
    sections: dict[str, Any] = {}
    source_receipts: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for name, contract in CONTRACTS.items():
        adapter = JsonArtifactAdapter(name, f"IIOS_{name.upper()}_SANITIZED_ARTIFACT",
                                      stale_after_seconds=900, timeout_seconds=2, fixture=fixture)
        result = adapter.read(paths.get(name))
        if result.data is None:
            pass
        else:
            mapped = contract.map(result.data)
            sections[SOURCE_SECTION[name]] = {"observed_at": mapped["observed_at"], "complete": mapped["complete"],
                                              "data": mapped["data"] | {"mapping_errors": mapped["errors"],
                                                                        "source_schema_version": mapped["schema_version"]}}
        cross_source_duplicate = bool(result.content_hash and result.content_hash in seen_hashes)
        if result.content_hash:
            seen_hashes.add(result.content_hash)
        source_receipts.append({"source": name, "state": result.state, "content_hash": result.content_hash,
                                "duplicate": result.duplicate or cross_source_duplicate, "error": result.error, "fixture": fixture})
    benchmark = sections.get("benchmark_9h", {}).get("data", {})
    shadow = sections.get("shadow_9i", {}).get("data", {})
    benchmark_session = benchmark.get("session_id")
    shadow_sessions = shadow.get("session_ids") or []
    if benchmark_session and shadow_sessions and benchmark_session not in shadow_sessions:
        sections["shadow_9i"]["complete"] = False
        shadow.setdefault("mapping_errors", []).append("CROSS_SESSION_MISMATCH")
    projection = build_living_wall_projection(sections, now=now)
    projection.update({"mode": "FIXTURE_NON_LIVE" if fixture else "READ_ONLY", "composed_at": (now or datetime.now(timezone.utc)).isoformat(),
                       "source_receipts": source_receipts, "bounded_source_count": len(paths)})
    return projection
