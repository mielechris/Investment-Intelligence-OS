from __future__ import annotations

from typing import Any

PRIORITY = ["SAFETY_AND_AUTHORITY", "MARKET_COLLECTION", "PAPER_PORTFOLIO_AND_ACTIVE_CASES",
            "INDEPENDENT_EVALUATION", "CURRENT_CANDIDATE_RESEARCH", "INTERVIEW_LIBRARY_INGESTION",
            "HISTORICAL_ANALYSIS", "VISUAL_DECORATION"]


def owner_report(kind: str, projection: dict[str, Any], approvals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if kind not in {"OPENING_READINESS", "CLOSING_PERFORMANCE", "DAILY_OWNER_SUMMARY"}:
        raise ValueError("unknown report kind")
    sections = projection.get("sections") if isinstance(projection.get("sections"), dict) else {}
    exceptions = [{"section": key, "state": value.get("state", "UNKNOWN")}
                  for key, value in sections.items() if value.get("state") not in {"CURRENT", "AVAILABLE"}]
    return {"kind": kind, "truth_schema": projection.get("schema_version", "UNKNOWN"), "exceptions": exceptions,
            "approval_inbox": approvals or [], "priority_order": PRIORITY, "paper_only": True,
            "live_execution_authority": False, "generated_from_sanitized_projection": True}
