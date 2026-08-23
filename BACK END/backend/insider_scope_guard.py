from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


RECENT_WINDOW_DAYS = 90
CLUSTER_WINDOW_DAYS = 30


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
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sorted_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    floor = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(records, key=lambda item: _record_date(item) or floor, reverse=True)


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


def _freshness(records: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    """Describe whether the stored insider dataset is current enough for present-tense use.

    A stale dataset is not evidence of zero recent activity. When the newest known row is
    older than the 90-day current window, current buy/sell counts must be UNKNOWN.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dated = [(item, _record_date(item)) for item in records]
    dated = [(item, stamp) for item, stamp in dated if stamp is not None]
    if not dated:
        return {
            "recent_window_days": RECENT_WINDOW_DAYS,
            "latest_record_at": None,
            "latest_record_age_days": None,
            "recent_activity_covered": False,
            "historical_only": bool(records),
        }
    newest = max(stamp for _, stamp in dated)
    age_days = max(0, int((now - newest).total_seconds() // 86400))
    covered = newest >= now - timedelta(days=RECENT_WINDOW_DAYS)
    return {
        "recent_window_days": RECENT_WINDOW_DAYS,
        "latest_record_at": newest.isoformat(),
        "latest_record_age_days": age_days,
        "recent_activity_covered": covered,
        "historical_only": not covered,
    }


def install_insider_scope_guard(module: Any) -> None:
    """Filter wrong-subject rows and make source scope/freshness explicit.

    Existing contaminated or stale rows remain in the immutable audit ledger. They are
    excluded from current-signal semantics without destructive deletion.
    """
    original_evidence = module.insider_evidence

    def scoped_status(case_id: str) -> dict[str, Any]:
        module._require_case(case_id)
        all_records = module.list_objects(case_id, "insider_activity_record")
        records = [item for item in all_records if _in_scope(item)]
        excluded = [item for item in all_records if not _in_scope(item)]
        records_sorted = _sorted_records(records)

        buys = [item for item in records if item.get("transaction_nature") == "OPEN_MARKET_PURCHASE"]
        sales = [item for item in records if item.get("transaction_nature") == "OPEN_MARKET_SALE"]
        planned_sales = [item for item in sales if item.get("plan_10b5_1") is True]
        ownership = [item for item in records if item.get("record_kind") == "BENEFICIAL_OWNERSHIP_FILING"]
        coverage = _coverage(records)
        freshness = _freshness(records)
        coverage.update(freshness)

        now = datetime.now(timezone.utc)
        recent_start = now - timedelta(days=RECENT_WINDOW_DAYS)
        cluster_start = now - timedelta(days=CLUSTER_WINDOW_DAYS)
        recent_records = [item for item in records_sorted if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= recent_start]
        historical_records = [item for item in records_sorted if item not in recent_records]
        recent_buys = [item for item in recent_records if item.get("transaction_nature") == "OPEN_MARKET_PURCHASE"]
        recent_sales = [item for item in recent_records if item.get("transaction_nature") == "OPEN_MARKET_SALE"]
        cluster_buys = [item for item in buys if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= cluster_start]
        cluster_sales = [item for item in sales if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= cluster_start]
        buy_owners = {str(item.get("reporting_owner") or "") for item in cluster_buys if item.get("reporting_owner")}
        sale_owners = {str(item.get("reporting_owner") or "") for item in cluster_sales if item.get("reporting_owner")}

        recent_covered = bool(freshness["recent_activity_covered"])
        cluster = "UNKNOWN_STALE_SOURCE" if not recent_covered else "NONE"
        if recent_covered and len(buy_owners) >= 2:
            cluster = "OPEN_MARKET_BUY_CLUSTER"
        elif recent_covered and len(sale_owners) >= 3:
            cluster = "OPEN_MARKET_SELL_CLUSTER"

        return {
            "case_id": case_id,
            "records": records_sorted[:40],
            "recent_records_90d": recent_records[:40] if recent_covered else [],
            "historical_records": historical_records[:40] if not recent_covered else records_sorted[40:80],
            "summary": {
                "record_count": len(records),
                "raw_record_count": len(all_records),
                "excluded_non_corporate_records": len(excluded),
                # Historical totals are preserved for context/audit.
                "open_market_buys": len(buys),
                "open_market_sales": len(sales),
                "buy_dollar_value": round(sum(float(item.get("dollar_value") or 0.0) for item in buys), 2),
                "sale_dollar_value": round(sum(float(item.get("dollar_value") or 0.0) for item in sales), 2),
                # Present-tense metrics are null when current-window coverage is stale.
                "recent_open_market_buys_90d": len(recent_buys) if recent_covered else None,
                "recent_open_market_sales_90d": len(recent_sales) if recent_covered else None,
                "recent_buy_dollar_value_90d": round(sum(float(item.get("dollar_value") or 0.0) for item in recent_buys), 2) if recent_covered else None,
                "recent_sale_dollar_value_90d": round(sum(float(item.get("dollar_value") or 0.0) for item in recent_sales), 2) if recent_covered else None,
                "planned_10b5_1_sales": len(planned_sales) if coverage["plan_10b5_1_covered"] else None,
                "beneficial_ownership_filings": len(ownership) if coverage["beneficial_ownership_covered"] else None,
                "cluster_signal_30d": cluster,
                "cluster_is_context_only": True,
            },
            "coverage": coverage,
            "paper_mode": True,
            "trade_execution_permission": False,
        }

    def scoped_evidence(case_id: str) -> list[dict[str, Any]]:
        # The core evidence function already excludes CONTEXT_ONLY secondary records.
        # Apply subject and freshness guards as defense in depth. Stale corporate rows
        # remain auditable context but cannot enter present-tense governed research.
        all_records = module.list_objects(case_id, "insider_activity_record")
        in_scope = [item for item in all_records if _in_scope(item)]
        freshness = _freshness(in_scope)
        if not freshness["recent_activity_covered"]:
            return []
        recent_start = datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS)
        allowed_ids = {
            str(item.get("insider_activity_id") or "")
            for item in in_scope
            if (_record_date(item) or datetime.min.replace(tzinfo=timezone.utc)) >= recent_start
        }
        return [
            item for item in original_evidence(case_id)
            if str(item.get("insider_activity_id") or "") in allowed_ids
        ]

    module.insider_status = scoped_status
    module.insider_evidence = scoped_evidence
