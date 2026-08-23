from __future__ import annotations

from typing import Any


CONTRACTS = {
    "memory_pricing": {
        "label": "Memory Pricing",
        "match_terms": ("hbm", "dram", "nand", "prices"),
        "match_min": 3,
        "minimum_fraction": 0.75,
        "facts": [
            {"key": "hbm_pricing", "label": "HBM pricing", "terms": ("hbm", "price", "pricing")},
            {"key": "dram_pricing", "label": "DRAM pricing", "terms": ("dram", "price", "pricing")},
            {"key": "nand_pricing", "label": "NAND pricing", "terms": ("nand", "price", "pricing")},
            {"key": "independent_sources", "label": "Two unrelated pricing sources", "terms": ("independent", "unrelated", "source")},
        ],
    },
    "supply_inventory": {
        "label": "Supply / Inventory",
        "match_terms": ("inventory days", "bit shipments", "wafer starts", "utilization", "capacity additions"),
        "match_min": 2,
        "minimum_fraction": 0.75,
        "facts": [
            {"key": "inventory", "label": "Inventory", "terms": ("inventory",)},
            {"key": "bit_shipments", "label": "Bit shipments", "terms": ("bit shipment", "shipments")},
            {"key": "wafer_starts", "label": "Wafer starts", "terms": ("wafer start", "wafer")},
            {"key": "utilization", "label": "Utilization", "terms": ("utilization",)},
            {"key": "capacity", "label": "Capacity additions", "terms": ("capacity",)},
            {"key": "hbm_packaging_yield", "label": "HBM packaging / yields", "terms": ("hbm", "packaging", "yield")},
        ],
    },
    "hyperscaler_demand": {
        "label": "Hyperscaler Demand",
        "match_terms": ("hyperscaler", "ai-capex", "server shipments", "backlog", "cancellations"),
        "match_min": 2,
        "minimum_fraction": 0.70,
        "facts": [
            {"key": "ai_capex", "label": "AI capex plans", "terms": ("ai", "capex", "capital expenditure")},
            {"key": "server_activity", "label": "Server shipments / utilization", "terms": ("server", "shipment", "utilization")},
            {"key": "backlog", "label": "Backlog", "terms": ("backlog",)},
            {"key": "cancellations", "label": "Cancellations / pushouts", "terms": ("cancellation", "pushout", "push-out")},
            {"key": "memory_terms", "label": "Memory content / enforceable terms", "terms": ("memory content", "customer agreement", "strategic agreement", "enforceable")},
        ],
    },
    "micron_financials": {
        "label": "Micron Filing Financials",
        "match_terms": ("micron", "filing-based", "revenue mix", "free cash flow", "debt and cash"),
        "match_min": 2,
        "minimum_fraction": 0.75,
        "facts": [
            {"key": "revenue", "label": "Revenue / revenue mix", "terms": ("revenue",)},
            {"key": "hbm_margin", "label": "HBM volumes / margins", "terms": ("hbm", "margin", "gross profit")},
            {"key": "inventory", "label": "Inventory", "terms": ("inventory",)},
            {"key": "cash_flow", "label": "Cash flow", "terms": ("cash flow", "operating activities")},
            {"key": "cash", "label": "Cash", "terms": ("cash and cash equivalents", "cash=")},
            {"key": "debt", "label": "Debt", "terms": ("debt",)},
            {"key": "capex", "label": "Capex", "terms": ("capex", "property plant and equipment", "payments to acquire")},
            {"key": "asp_sensitivity", "label": "ASP sensitivity", "terms": ("asp", "average selling price", "pricing sensitivity")},
        ],
    },
    "valuation_market": {
        "label": "MU Valuation / Market",
        "match_terms": ("current mu price", "diluted shares", "consensus revenue", "valuation multiples", "short interest"),
        "match_min": 2,
        "minimum_fraction": 0.70,
        "facts": [
            {"key": "market_price", "label": "Current MU price", "terms": ("mu.us", "market price", "current price")},
            {"key": "diluted_shares", "label": "Diluted shares", "terms": ("diluted shares", "weightedaveragenumberofdiluted")},
            {"key": "consensus", "label": "Revenue / EPS consensus", "terms": ("consensus", "eps estimate", "revenue estimate")},
            {"key": "valuation", "label": "Valuation multiple", "terms": ("valuation", "multiple", "p/e", "ev/")},
            {"key": "short_interest", "label": "Short interest", "terms": ("short interest", "shares short")},
            {"key": "options", "label": "Options positioning", "terms": ("options", "put/call", "open interest")},
        ],
    },
    "policy": {
        "label": "Policy / Regulation",
        "match_terms": ("semiconductor incentives", "export controls", "tariffs", "permitting", "effective dates"),
        "match_min": 2,
        "minimum_fraction": 0.70,
        "facts": [
            {"key": "incentives", "label": "Semiconductor incentives", "terms": ("incentive", "chips", "award")},
            {"key": "export_controls", "label": "Export controls", "terms": ("export control", "bis", "advanced computing")},
            {"key": "tariffs", "label": "Tariffs", "terms": ("tariff",)},
            {"key": "effective_dates", "label": "Effective dates", "terms": ("effective date", "effective", "publication date")},
            {"key": "transmission", "label": "Supply-demand transmission", "terms": ("supply", "demand", "capacity", "procurement")},
        ],
    },
}


def _blob(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("claim", "title", "source", "primary_fact_key", "metric")
    ).lower()


def contract_for_requirement(requirement: str) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    lowered = str(requirement or "").lower()
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for key, contract in CONTRACTS.items():
        score = sum(1 for term in contract["match_terms"] if term in lowered)
        if score >= int(contract.get("match_min", 1)):
            ranked.append((score, key, contract))
    if not ranked:
        return None, None
    ranked.sort(key=lambda row: row[0], reverse=True)
    _, key, contract = ranked[0]
    return key, contract


def fact_matches(item: dict[str, Any], fact: dict[str, Any]) -> bool:
    explicit = str(item.get("primary_fact_key") or "").strip()
    if explicit and explicit == fact["key"]:
        return True
    text = _blob(item)
    terms = tuple(str(term).lower() for term in fact.get("terms") or ())
    if not terms:
        return False
    hits = sum(1 for term in terms if term in text)
    return hits >= (1 if len(terms) == 1 else 2)


def coverage_for_requirement(requirement: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    lane, contract = contract_for_requirement(requirement)
    if not contract:
        return None
    covered: list[str] = []
    missing: list[str] = []
    fact_rows: list[dict[str, Any]] = []
    for fact in contract["facts"]:
        matches = [item for item in items if fact_matches(item, fact)]
        if matches:
            covered.append(fact["key"])
        else:
            missing.append(fact["key"])
        fact_rows.append({
            "key": fact["key"],
            "label": fact["label"],
            "covered": bool(matches),
            "supporting_items": len(matches),
        })
    total = len(contract["facts"])
    ratio = len(covered) / total if total else 0.0
    return {
        "lane": lane,
        "label": contract["label"],
        "covered_fact_keys": covered,
        "missing_fact_keys": missing,
        "covered_facts": len(covered),
        "total_facts": total,
        "coverage_ratio": round(ratio, 4),
        "minimum_fraction": float(contract["minimum_fraction"]),
        "coverage_gate_passed": ratio >= float(contract["minimum_fraction"]),
        "facts": fact_rows,
    }
