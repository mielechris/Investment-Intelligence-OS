from __future__ import annotations

from typing import Any


def normalize_secondary_institutional_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize secondary institutional records into one honest governed schema.

    Secondary fallbacks are useful context, but their units and semantics differ from
    the primary Yahoo modules. This guard prevents those differences from becoming
    false freshness, false percentages, or overstated analyst-evidence claims.
    """
    updated = dict(record)
    if not updated.get("secondary_source") and updated.get("source_tier") != "SECONDARY_PUBLIC_CONTEXT":
        return updated

    details = dict(updated.get("details") or {})
    lane = str(updated.get("lane") or "")
    fallback_scope = str(details.get("fallback_scope") or "").lower()

    if lane == "institutional_ownership":
        # A generic page timestamp is not a 13F report date. Unless the fallback parser
        # can prove the actual reporting date, the record must remain lagged context.
        details["reporting_date_unknown"] = True
        details["reporting_lag_status"] = "UNVERIFIED_13F_REPORT_DATE"
        updated["data_as_of"] = None
        updated["age_days"] = None
        updated["fresh"] = False
        updated["admission_status"] = "LAGGED_CONTEXT"
        updated["freshness_state"] = "REPORT_DATE_UNVERIFIED"
        updated["summary"] = (
            "Secondary 13F ownership context is available, but the fallback source did "
            "not expose a verified 13F report date. Treat ownership direction as lagged "
            "historical context, not current positioning."
        )

    elif lane == "analyst_revisions" and "ratings and target changes" in fallback_scope:
        direction = str(updated.get("directional_context") or "UNKNOWN")
        if direction == "REVISION_BIAS_POSITIVE":
            direction = "RATING_TARGET_BIAS_POSITIVE"
        elif direction == "REVISION_BIAS_NEGATIVE":
            direction = "RATING_TARGET_BIAS_NEGATIVE"
        updated["directional_context"] = direction
        details["analyst_feed_kind"] = "RATINGS_AND_TARGET_ACTIONS"
        details["true_eps_revision_series"] = False

    elif lane == "short_interest":
        # Primary Yahoo fields are decimal fractions; MarketBeat publishes percentages.
        # Normalize the fallback to the same decimal representation expected by the UI.
        short_pct = details.get("short_percent_float")
        if isinstance(short_pct, (int, float)) and abs(float(short_pct)) > 1:
            details["short_percent_float"] = float(short_pct) / 100.0

        raw_change = details.get("change_pct")
        if isinstance(raw_change, (int, float)):
            normalized_change = float(raw_change) / 100.0 if abs(float(raw_change)) > 1 else float(raw_change)
            details["change_vs_prior_month"] = normalized_change
        elif "change_vs_prior_month" not in details:
            details["change_vs_prior_month"] = None

        if "short_ratio" not in details:
            details["short_ratio"] = details.get("days_to_cover")
        if "shares_short_prior_month" not in details:
            details["shares_short_prior_month"] = details.get("shares_short_prior")
        details["percentage_schema"] = "DECIMAL_FRACTION"

    updated["details"] = details
    return updated


def install_institutional_integrity_guard(module: Any) -> None:
    prior_auto = module.auto_capture_institutional
    prior_status = module.institutional_status
    prior_evidence = module.institutional_evidence

    def _persist(record: dict[str, Any]) -> None:
        record_id = str(record.get("institutional_signal_id") or "")
        case_id = str(record.get("case_id") or "")
        if not record_id or not case_id:
            return
        module.record_object(
            record_id,
            "institutional_signal_record",
            case_id,
            record,
            parent_id=record.get("institutional_snapshot_id"),
            topic=record.get("topic"),
        )

    def auto_capture_with_integrity(case_id: str) -> dict[str, Any]:
        result = prior_auto(case_id)
        normalized_records: list[dict[str, Any]] = []
        repaired_lanes: list[str] = []
        for record in result.get("records") or []:
            normalized = normalize_secondary_institutional_record(record)
            if normalized != record:
                repaired_lanes.append(str(normalized.get("lane") or ""))
                _persist(normalized)
            normalized_records.append(normalized)
        if repaired_lanes:
            module.record_event(
                case_id,
                "INSTITUTIONAL_INTEGRITY_NORMALIZED",
                entity_id=result.get("institutional_snapshot_id"),
                payload={"repaired_lanes": repaired_lanes},
            )
        return {**result, "records": normalized_records, "integrity_repaired_lanes": repaired_lanes}

    def status_with_integrity(case_id: str) -> dict[str, Any]:
        result = prior_status(case_id)
        lanes = dict(result.get("lanes") or {})
        for lane_key, lane_status in list(lanes.items()):
            lane_copy = dict(lane_status or {})
            record = lane_copy.get("record")
            if isinstance(record, dict):
                normalized = normalize_secondary_institutional_record(record)
                lane_copy["record"] = normalized
                if normalized.get("admission_status") == "LAGGED_CONTEXT":
                    lane_copy["status"] = "LAGGED"
            lanes[lane_key] = lane_copy
        return {**result, "lanes": lanes}

    def evidence_with_integrity(case_id: str) -> list[dict[str, Any]]:
        """Protect Gap Hunter from legacy pre-v0.11.2 fallback rows already in ledger."""
        output: list[dict[str, Any]] = []
        for item in prior_evidence(case_id):
            source = str(item.get("source") or "").lower()
            lane = str(item.get("institutional_lane") or "")
            if "marketbeat" not in source:
                output.append(item)
                continue
            # Unknown 13F report dates cannot be treated as fresh present-tense evidence.
            if lane == "institutional_ownership":
                continue
            normalized = dict(item)
            if lane == "analyst_revisions":
                direction = str(normalized.get("directional_context") or "")
                if direction == "REVISION_BIAS_POSITIVE":
                    normalized["directional_context"] = "RATING_TARGET_BIAS_POSITIVE"
                elif direction == "REVISION_BIAS_NEGATIVE":
                    normalized["directional_context"] = "RATING_TARGET_BIAS_NEGATIVE"
            output.append(normalized)
        return output

    module.auto_capture_institutional = auto_capture_with_integrity
    module.institutional_status = status_with_integrity
    module.institutional_evidence = evidence_with_integrity
