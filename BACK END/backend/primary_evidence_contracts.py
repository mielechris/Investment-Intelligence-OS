from __future__ import annotations

import re
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
        "minimum_fraction": 1.0,
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
    "micron_hbm_economics": {
        "label": "Micron HBM Economics",
        "match_terms": (
            "micron hbm", "hbm revenue", "shipment volumes", "margins",
            "customer concentration", "capacity allocation", "asp sensitivity",
        ),
        "match_min": 3,
        "minimum_fraction": 1.0,
        "facts": [
            {"key": "hbm_revenue", "label": "HBM revenue", "terms": ("hbm", "revenue")},
            {"key": "hbm_shipments", "label": "HBM shipment / volume ramp", "terms": ("hbm", "shipment", "volume ramp", "high-volume")},
            {"key": "hbm_margin", "label": "HBM margin / economic contribution", "terms": ("hbm", "margin", "gross margin", "higher-margin")},
            {"key": "customer_concentration", "label": "HBM customer concentration", "terms": ("hbm", "customer", "concentration", "customer base")},
            {"key": "capacity_allocation", "label": "HBM capacity allocation", "terms": ("hbm", "capacity", "allocation", "wafer", "supply")},
            {"key": "hbm_asp_sensitivity", "label": "HBM pricing / ASP sensitivity", "terms": ("hbm", "price", "pricing", "premium", "average selling price")},
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
        "match_terms": (
            "semiconductor incentives", "export controls", "tariff", "tariffs", "permitting",
            "effective dates", "implementation guidance", "transmission", "substitution",
        ),
        "match_min": 2,
        "minimum_fraction": 0.70,
        "facts": [
            {"key": "incentives", "label": "Semiconductor incentives", "terms": ("incentive", "chips", "award")},
            {"key": "export_controls", "label": "Export controls", "terms": ("export control", "bis", "advanced computing")},
            {"key": "tariffs", "label": "Tariffs", "terms": ("tariff",)},
            {"key": "effective_dates", "label": "Effective dates", "terms": ("effective date", "effective", "publication date")},
            {"key": "transmission", "label": "Measured supply-demand transmission", "terms": ("imports", "shipments", "production", "utilization", "market share", "prices", "volume", "inventory", "substitution")},
        ],
    },
}


SUPPLY_SUPPLIER_ALIASES: tuple[tuple[str, str], ...] = (
    ("micron", "Micron"),
    ("sk hynix", "SK hynix"),
    ("samsung", "Samsung"),
    ("cxmt", "CXMT"),
)


def _blob(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("claim", "title", "source", "url", "supplier", "primary_fact_key", "metric")
    ).lower()


def _supply_supplier_from_item(item: dict[str, Any]) -> str | None:
    text = _blob(item)
    for token, canonical in SUPPLY_SUPPLIER_ALIASES:
        if token in text:
            return canonical
    return None


def _required_supply_suppliers(requirement: str) -> list[str]:
    lowered = str(requirement or "").lower()
    return [canonical for token, canonical in SUPPLY_SUPPLIER_ALIASES if token in lowered]


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


def _measured_transmission_match(item: dict[str, Any]) -> bool:
    """Policy text proves a rule exists; it does not prove the rule changed the market.

    Measured transmission needs a quantitative outcome observation from a source other
    than the policy-issuing pages themselves. Examples include imports, shipments,
    production, utilization, market share, prices, volume, inventory, or substitution.
    """
    text = _blob(item)
    policy_only_hosts = ("whitehouse.gov", "bis.gov", "federalregister.gov", "nist.gov")
    if any(host in text for host in policy_only_hosts):
        return False
    outcome_terms = (
        "imports", "shipments", "production", "output", "utilization", "market share",
        "prices", "price", "volume", "inventory", "substitution", "sourcing", "capacity",
    )
    if not any(term in text for term in outcome_terms):
        return False
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|million|billion|thousand|units|bps)?\b", text))


def fact_matches(item: dict[str, Any], fact: dict[str, Any]) -> bool:
    explicit = str(item.get("primary_fact_key") or "").strip()
    if fact.get("key") == "transmission":
        return _measured_transmission_match(item)

    # Governed primary-evidence records are single-purpose once classified. Without this
    # guard, a shipment record containing words such as "customer" could also satisfy a
    # customer-concentration fact, creating cross-fact contamination. Unclassified/raw
    # evidence may still use semantic term matching below.
    if explicit:
        return explicit == fact["key"]

    text = _blob(item)
    terms = tuple(str(term).lower() for term in fact.get("terms") or ())
    if not terms:
        return False
    hits = sum(1 for term in terms if term in text)
    return hits >= (1 if len(terms) == 1 else 2)


def _critical_fact_keys(requirement: str, lane: str) -> set[str]:
    """Facts explicitly demanded by the Committee are mandatory even above % thresholds."""
    lowered = str(requirement or "").lower()
    critical: set[str] = set()
    if lane == "policy" and any(term in lowered for term in ("measurable", "transmission", "substitution", "supply-chain")):
        critical.add("transmission")
    if lane == "micron_hbm_economics":
        critical.update(fact["key"] for fact in CONTRACTS[lane]["facts"])
    return critical


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
    critical_keys = _critical_fact_keys(requirement, lane)
    missing_critical = sorted(key for key in critical_keys if key not in covered)

    required_suppliers: list[str] = []
    covered_suppliers: list[str] = []
    missing_suppliers: list[str] = []
    if lane == "supply_inventory":
        required_suppliers = _required_supply_suppliers(requirement)
        supplier_set = {
            supplier for supplier in (_supply_supplier_from_item(item) for item in items)
            if supplier
        }
        covered_suppliers = [supplier for supplier in required_suppliers if supplier in supplier_set]
        missing_suppliers = [supplier for supplier in required_suppliers if supplier not in supplier_set]

    threshold_passed = ratio >= float(contract["minimum_fraction"])
    coverage_gate_passed = threshold_passed and not missing_critical and not missing_suppliers
    return {
        "lane": lane,
        "label": contract["label"],
        "covered_fact_keys": covered,
        "missing_fact_keys": missing,
        "covered_facts": len(covered),
        "total_facts": total,
        "coverage_ratio": round(ratio, 4),
        "minimum_fraction": float(contract["minimum_fraction"]),
        "threshold_passed": threshold_passed,
        "critical_fact_keys": sorted(critical_keys),
        "missing_critical_fact_keys": missing_critical,
        "required_suppliers": required_suppliers,
        "covered_suppliers": covered_suppliers,
        "missing_suppliers": missing_suppliers,
        "supplier_coverage_gate_passed": not missing_suppliers,
        "coverage_gate_passed": coverage_gate_passed,
        "all_facts_covered": len(covered) == total,
        "facts": fact_rows,
    }
