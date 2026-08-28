from __future__ import annotations

from typing import Any


LANE_HINTS: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    (
        "micron_financials",
        (
            ("micron", "10-q"),
            ("micron", "earnings", "guidance"),
            ("cash flow", "capex", "debt"),
            ("revenue", "inventory", "margin"),
            ("earnings", "margin", "capex"),
        ),
    ),
    (
        "micron_hbm_economics",
        (
            ("hbm", "margin"),
            ("hbm", "customer concentration"),
            ("hbm", "capacity", "asp"),
            ("hbm", "shipment", "revenue"),
        ),
    ),
    (
        "memory_pricing",
        (
            ("hbm", "dram", "pricing"),
            ("hbm", "nand", "pricing"),
            ("memory", "pricing", "supply-demand"),
            ("negotiated pricing", "dram"),
        ),
    ),
    (
        "supply_inventory",
        (
            ("competitor capacity",),
            ("capacity plans",),
            ("customer qualification", "capacity"),
            ("inventory", "capacity", "yield"),
            ("samsung", "sk hynix"),
        ),
    ),
    (
        "hyperscaler_demand",
        (
            ("server-demand",),
            ("hyperscaler-capex",),
            ("backlog-conversion",),
            ("customer-inventory", "channel-inventory"),
            ("end consumption", "restocking"),
        ),
    ),
    (
        "valuation_market",
        (
            ("forward consensus",),
            ("normalized-cycle", "valuation"),
            ("ohlcv",),
            ("volatility", "options", "short-interest"),
            ("support/resistance",),
            ("liquidity", "flows", "catalyst-calendar"),
        ),
    ),
    (
        "policy",
        (
            ("export-control",),
            ("export control",),
            ("tariff",),
            ("chips", "incentive"),
        ),
    ),
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def hinted_lanes(requirement: str) -> list[str]:
    text = _norm(requirement)
    lanes: list[str] = []
    for lane, alternatives in LANE_HINTS:
        if any(all(term in text for term in terms) for terms in alternatives):
            lanes.append(lane)
    return lanes


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _lane_snapshot(primary_module: Any, case_id: str, lane: str) -> dict[str, Any]:
    # Deep Watch may classify a broad Committee requirement into more than one governed
    # lane even when primary_evidence.contract_for_requirement picked only one. Calling
    # the module's lane-status primitive directly preserves all existing freshness,
    # semantic, source-grade and coverage rules for that lane.
    records = primary_module.list_objects(case_id, "primary_evidence_record")
    row = primary_module._lane_status(case_id, lane, records)
    facts = row.get("facts") if isinstance(row.get("facts"), list) else []
    covered = sorted(
        str(fact.get("key"))
        for fact in facts
        if isinstance(fact, dict) and fact.get("covered") is True
    )
    missing = sorted(
        str(fact.get("key"))
        for fact in facts
        if isinstance(fact, dict) and fact.get("covered") is not True
    )
    latest_ids = sorted(
        str(record.get("primary_evidence_id"))
        for record in row.get("latest_records") or []
        if isinstance(record, dict) and record.get("primary_evidence_id")
    )
    return {
        "kind": "PRIMARY_EVIDENCE",
        "lane": lane,
        "status": row.get("status") or "OPEN",
        "coverage_pct": int(row.get("coverage_pct") or 0),
        "covered_fact_keys": covered,
        "missing_fact_keys": missing,
        "current_high_quality_records": int(row.get("current_high_quality_records") or 0),
        "source_count": int(row.get("source_count") or 0),
        "latest_record_ids": latest_ids,
    }


def _aggregate_primary_snapshots(lanes: list[str], snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    covered: list[str] = []
    missing: list[str] = []
    total_facts = 0
    covered_facts = 0
    high_quality_records = 0
    source_count = 0

    for lane in lanes:
        row = snapshots[lane]
        lane_covered = [f"{lane}:{key}" for key in row.get("covered_fact_keys") or []]
        lane_missing = [f"{lane}:{key}" for key in row.get("missing_fact_keys") or []]
        covered.extend(lane_covered)
        missing.extend(lane_missing)
        covered_facts += len(lane_covered)
        total_facts += len(lane_covered) + len(lane_missing)
        high_quality_records += int(row.get("current_high_quality_records") or 0)
        source_count += int(row.get("source_count") or 0)

    pct = int(round((covered_facts / total_facts) * 100)) if total_facts else 0
    statuses = {str(row.get("status") or "OPEN") for row in snapshots.values()}
    if snapshots and statuses == {"COMPLETE_FACT_COVERAGE"}:
        status = "COMPLETE_FACT_COVERAGE"
    elif covered_facts:
        status = "PARTIAL"
    else:
        status = "OPEN"

    return {
        "kind": "PRIMARY_EVIDENCE",
        "lane": lanes[0] if len(lanes) == 1 else "MULTI_LANE",
        "lanes": lanes,
        "status": status,
        "coverage_pct": pct,
        "covered_fact_keys": sorted(covered),
        "missing_fact_keys": sorted(missing),
        "current_high_quality_records": high_quality_records,
        "source_count": source_count,
        "components": snapshots,
    }


def install_deep_watch_lane_mapping(module: Any) -> None:
    if getattr(module, "_structured_lane_mapping_installed", False):
        return

    original_classify = module.classify_requirement
    original_snapshot = module.obligation_snapshot

    def classify_requirement(requirement: str) -> dict[str, Any]:
        base = original_classify(requirement)
        if base.get("kind") == "PORTFOLIO_CONTEXT":
            return {**base, "mapping_version": "structured-v2"}

        lanes = hinted_lanes(requirement)
        if base.get("kind") == "PRIMARY_EVIDENCE" and base.get("lane"):
            lanes.insert(0, str(base.get("lane")))
        lanes = _dedupe(lanes)

        if lanes:
            return {
                "kind": "PRIMARY_EVIDENCE",
                "lane": lanes[0],
                "lanes": lanes,
                "lane_label": " + ".join(lanes),
                "multi_lane": len(lanes) > 1,
                "mapping_version": "structured-v2",
            }

        return {**base, "mapping_version": "structured-v2"}

    def obligation_snapshot(primary_module: Any, case_id: str, requirement: str) -> dict[str, Any]:
        classification = classify_requirement(requirement)
        lanes = [str(value) for value in classification.get("lanes") or [] if str(value)]
        if classification.get("kind") == "PRIMARY_EVIDENCE" and lanes:
            snapshots = {lane: _lane_snapshot(primary_module, case_id, lane) for lane in lanes}
            return _aggregate_primary_snapshots(lanes, snapshots)
        return original_snapshot(primary_module, case_id, requirement)

    module.classify_requirement = classify_requirement
    module.obligation_snapshot = obligation_snapshot
    module._structured_lane_mapping_installed = True
