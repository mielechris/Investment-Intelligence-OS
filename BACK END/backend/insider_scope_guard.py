from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


def _is_non_corporate_secondary(record: dict[str, Any]) -> bool:
    if not record.get("secondary_source"):
        return False
    blob = " ".join(
        str(record.get(key) or "")
        for key in ("reporting_owner", "reporting_owner_role", "description")
    )
    upper = re.sub(r"\s+", " ", blob).upper()
    if any(term in upper for term in (
        " SENATE ", " HOUSE ", " SENATOR ", " REPRESENTATIVE ",
        " CONGRESS ", " CONGRESSMAN ", " CONGRESSWOMAN ",
    )):
        return True
    if re.search(r"\b(?:HOUSE|SENATE)\s*\([RID]-[A-Z]{2}\)", upper):
        return True
    return False


def _in_scope(record: dict[str, Any]) -> bool:
    if record.get("subject_scope") == "EXCLUDED_NON_CORPORATE":
        return False
    return not _is_non_corporate_secondary(record)


def _record_date(record: dict[str, Any]) -> datetime | None:
    value = str(record.get("transaction_date") or record.get("filing_date") or "").strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [r for r in records if r.get("source_type") == "filing" and not r.get("fallback_source") and not r.get("secondary_source")]
    official = [r for r in records if r.get("fallback_source") and not r.get("secondary_source")]
    secondary = [r for r in records if r.get("secondary_source")]
    if primary:
        tier = "PRIMARY_SEC"
    elif official:
        tier = "OFFICIAL_COMPANY_FALLBACK"
    elif secondary:
        tier = "SECONDARY_PUBLIC_CONTEXT"
    else:
        tier = "NO_SUCCESSFUL_SOURCE"
    return {
        "active_source_tier": tier,
        "primary_sec_records": len(primary),
        "official_company_records": len(official),
        "secondary_public_records": len(secondary),
        "open_market_direction_covered": bool(primary or secondary),
        "plan_10b5_1_covered": bool(primary),
        "beneficial_ownership_covered": bool(primary or official),
        "secondary_requires_primary_corroboration": bool(secondary),
    }


def install_insider_scope_guard(module: Any) -> None:
    """Filter wrong-subject rows and make summary coverage explicit.

    Existing contaminated rows remain in the immutable audit ledger. This guard excludes
    them from user-facing counts and any research evidence without destructive deletion.
    """
    original_evidence = module.insider_evidence

    def scoped_status(case_id: str) -> dict[str, Any]:
        module._require_case(case_id)
        all_records = module.list_objects(case_id, "insider_activity_record")
        records = [item for item in all_records if _in_scope(item)]
        excluded = [item for item in all_records if not _in_scope(item)]

        buys = [item for item in records if item.get("transaction_nature") == "OPEN_MARKET_PURCHASE"]
        sales = [item for item in records if item.get("transaction_nature") == "OPEN_MARKET_SALE"]
        planned_sales = [item for item in sales if item.get("plan_10b5_1") is True]
        ownership = [item for item in records if item.get("record_kind") == "BENEFICIAL_OWNERSHIP_FILING"]
        coverage = _coverage(records)

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=30)
        recent_buys = [item for item in buys if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start]
        recent_sales = [item for item in sales if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= window_start]
        buy_owners = {str(item.get("reporting_owner") or "") for item in recent_buys if item.get("reporting_owner")}
        sale_owners = {str(item.get("reporting_owner") or "") for item in recent_sales if item.get("reporting_owner")}
        cluster = "NONE"
        if len(buy_owners) >= 2:
            cluster = "OPEN_MARKET_BUY_CLUSTER"
        elif len(sale_owners) >= 3:
            cluster = "OPEN_MARKET_SELL_CLUSTER"

        return {
            "case_id": case_id,
            "records": list(reversed(records[-40:])),
            "summary": {
                "record_count": len(records),
                "raw_record_count": len(all_records),
                "excluded_non_corporate_records": len(excluded),
                "open_market_buys": len(buys),
                "open_market_sales": len(sales),
                "planned_10b5_1_sales": len(planned_sales) if coverage["plan_10b5_1_covered"] else None,
                "beneficial_ownership_filings": len(ownership) if coverage["beneficial_ownership_covered"] else None,
                "buy_dollar_value": round(sum(float(item.get("dollar_value") or 0.0) for item in buys), 2),
                "sale_dollar_value": round(sum(float(item.get("dollar_value") or 0.0) for item in sales), 2),
                "cluster_signal_30d": cluster,
                "cluster_is_context_only": True,
            },
            "coverage": coverage,
            "paper_mode": True,
            "trade_execution_permission": False,
        }

    def scoped_evidence(case_id: str) -> list[dict[str, Any]]:
        # The core evidence function already excludes CONTEXT_ONLY secondary records.
        # Apply the subject guard as a second defense for any future source tier.
        allowed_ids = {
            str(item.get("insider_activity_id") or "")
            for item in module.list_objects(case_id, "insider_activity_record")
            if _in_scope(item)
        }
        return [
            item for item in original_evidence(case_id)
            if str(item.get("insider_activity_id") or "") in allowed_ids
        ]

    module.insider_status = scoped_status
    module.insider_evidence = scoped_evidence
