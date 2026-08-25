from __future__ import annotations

from typing import Any


def apply_latest_decision_lineage(
    row: dict[str, Any],
    *,
    decision: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make the dashboard describe one coherent research state.

    Committee decisions are the authoritative source for disposition, confidence, and
    the evidence packet actually used by the Committee. A monitor snapshot is only a
    fallback when no Committee evidence summary exists. Qualification state may refine
    the latest action only when it belongs to the same Committee decision.
    """
    output = dict(row)
    decision = decision or {}
    qualification = qualification or {}

    decision_summary = decision.get("evidence_summary") or {}
    snapshot_summary = ((snapshot or {}).get("evidence_packet") or {}).get("summary") or {}

    if decision:
        output["committee_disposition"] = decision.get("disposition")
        output["committee_confidence"] = decision.get("confidence")
        output["latest_action"] = decision.get("disposition")
        output["latest_research_source"] = "COMMITTEE_DECISION"

    summary = decision_summary if decision_summary else snapshot_summary
    if "average_quality_score" in summary:
        output["evidence_quality"] = summary.get("average_quality_score")
        output["latest_evidence_count"] = summary.get("evidence_count")
        if not decision_summary:
            output["latest_research_source"] = "MONITOR_SNAPSHOT"

    same_decision = bool(decision) and str(qualification.get("decision_id") or "") == str(decision.get("decision_id") or "")
    if qualification and same_decision:
        output["qualification_stage"] = qualification.get("stage")
        output["qualified_buy_candidate"] = qualification.get("qualified_buy_candidate")
        output["latest_action"] = qualification.get("stage") or output.get("latest_action")

    return output
