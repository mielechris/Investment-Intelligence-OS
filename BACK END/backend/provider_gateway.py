"""Source-only gateway: explicit injected transports and offline stage callbacks.

No default transport, credentials, model clients, brokers or production imports.
This module cannot install or arm itself and cannot grant execution authority.
"""
from __future__ import annotations

from collections import Counter
from threading import Lock

from provider_gateway_adapters import ENDPOINTS, FEEDS, normalize
from provider_gateway_contract import (
    ADAPTER_VERSION, PROVIDER_ROLES, SCHEMA, content_hash, freshness,
    locked_authority, pin, safe_document, seal, symbols, utc, verify_receipt,
)

QUALIFICATIONS = ("credential_binding", "entitlement", "internal_use", "ticker_coverage",
                  "rate_limit", "cost_credit", "ambiguous_billing")
STAGES = ("GOVERNED_EVIDENCE", "CANDIDATES", "AGENTS_MODELS", "JOHNNY_NO_SKEPTIC",
          "COMMITTEE", "DETERMINISTIC_RISK", "ALPACA_PAPER_DECISION", "RECEIPT", "OUTCOME_LEARNING")


class ProviderGateway:
    """One shared request budget; instances are OFFLINE_ONLY, not live clients.

    A future runtime must supply independently qualified durable reservations and
    secure transports. In-memory test budgets are never runtime acceptance.
    """

    def __init__(self, *, policy, expected_policy, universe, expected_universe, transport, clock):
        safe_document(policy)
        safe_document(universe)
        pin(policy, expected_policy)
        pin(universe, expected_universe)
        symbols(universe["symbols"])
        if policy.get("mode") != "OFFLINE_ONLY" or policy.get("authority") != locked_authority():
            raise ValueError("OFFLINE_LOCK_REQUIRED")
        if not callable(transport) or not callable(clock):
            raise ValueError("INJECTED_BOUNDARY_REQUIRED")
        # Freeze caller-owned inputs through canonical copies.
        import json
        from truth_spine_contract import canonical
        self._policy = json.loads(canonical(policy))
        self._universe = json.loads(canonical(universe))
        self._parents = {"policy": expected_policy, "universe": expected_universe}
        self._transport, self._clock = transport, clock
        self._lock = Lock()
        self._used = set()
        self._counts = Counter()

    def _admit(self, request, start):
        safe_document(request)
        if set(request) != {"provider", "endpoint", "symbols", "feed", "request_id", "mode"}:
            raise ValueError("REQUEST_SCHEMA_INVALID")
        provider = request["provider"]
        if provider not in ENDPOINTS or request["endpoint"] not in ENDPOINTS[provider]:
            raise ValueError("ENDPOINT_DENIED")
        if request["feed"] not in FEEDS[provider] or request["mode"] not in ("FILTERED", "FULL_MARKET"):
            raise ValueError("EXPLICIT_FEED_MODE_REQUIRED")
        if request["mode"] == "FULL_MARKET" and provider != "MASSIVE":
            raise ValueError("FULL_MARKET_PROVIDER_INVALID")
        requested = symbols(request["symbols"])
        if not set(requested) <= set(self._universe["symbols"]):
            raise ValueError("OUTSIDE_GOVERNED_UNIVERSE")
        entry = self._policy.get("providers", {}).get(provider, {})
        if (entry.get("endpoint") != request["endpoint"] or entry.get("feed") != request["feed"]
                or entry.get("mode") != request["mode"] or entry.get("symbols") != requested):
            raise ValueError("ENDPOINT_FEED_SYMBOL_QUALIFICATION_REQUIRED")
        if any(entry.get(k) != "VERIFIED" for k in QUALIFICATIONS):
            raise ValueError("QUALIFICATION_UNVERIFIED")
        if not utc(entry["valid_from"]) <= utc(start) <= utc(entry["expires_at"]):
            raise ValueError("ACCOUNT_EVIDENCE_EXPIRED")
        for name in ("maximum_requests", "maximum_response_bytes", "maximum_age_seconds", "timeout_seconds"):
            if type(entry.get(name)) is not int or entry[name] <= 0:
                raise ValueError("BOUNDED_POLICY_REQUIRED")
        if entry["maximum_requests"] > 3 or entry["timeout_seconds"] > 20:
            raise ValueError("OFFLINE_BATCH_BOUND_EXCEEDED")
        if not isinstance(request["request_id"], str) or not request["request_id"]:
            raise ValueError("REQUEST_ID_REQUIRED")
        with self._lock:
            if request["request_id"] in self._used:
                raise ValueError("DUPLICATE_REQUEST_REJECTED")
            if self._counts[provider] >= entry["maximum_requests"]:
                raise ValueError("REQUEST_BUDGET_EXHAUSTED")
            self._used.add(request["request_id"])
            self._counts[provider] += 1  # Reservation survives timeout/ambiguity.
        return entry

    def collect(self, request, *, expected_request):
        """Exactly one injected exchange; never echo raw exception text."""
        import json
        from truth_spine_contract import canonical
        safe_document(request)
        pin(request, expected_request)
        request = json.loads(canonical(request))
        start = self._clock()
        entry = self._admit(request, start)
        parsed, raw_hash = None, None
        cost_state = "UNVERIFIED"
        failure, status = "NONE", None
        try:
            payload = self._transport(dict(request), timeout_seconds=entry["timeout_seconds"])
            safe_document(payload)
            encoded = canonical(payload)
            if len(encoded) > entry["maximum_response_bytes"]:
                raise ValueError("RESPONSE_TOO_LARGE")
            raw_hash = content_hash(payload)
            parsed = normalize(request["provider"], request["endpoint"], payload)
            status = parsed["status"]
        except TimeoutError:
            failure = "TIMEOUT_AMBIGUOUS_NO_RETRY"
        except Exception:
            failure = "RESPONSE_REJECTED_OR_AMBIGUOUS_NO_RETRY"
        end = self._clock()
        elapsed = (utc(end) - utc(start)).total_seconds()
        if elapsed < 0 or elapsed > entry["timeout_seconds"]:
            failure = "DEADLINE_OR_CLOCK_INVALID_NO_RETRY"
        if utc(end) > utc(entry["expires_at"]):
            failure = "ACCOUNT_EVIDENCE_EXPIRED_IN_FLIGHT"
        all_obs = parsed["observations"] if parsed else []
        requested = set(request["symbols"])
        returned = sorted({r["ticker"] for r in all_obs})
        unexpected = sorted(set(returned) - requested)
        observations = []
        for row in all_obs:
            fresh = freshness(row["event_time"], end, entry["maximum_age_seconds"])
            publication = row["publication_time"]
            if publication is not None:
                try:
                    if utc(publication) > utc(end):
                        fresh = "FUTURE"
                except ValueError:
                    fresh = "UNVERIFIED"
            if request["provider"] == "BIGDATA" and (not row["source_references"] or publication is None):
                fresh = "UNVERIFIED"
            observations.append({**row, "observation_time": row["event_time"], "retrieval_time": end,
                                 "freshness": fresh, "governed": row["ticker"] in requested,
                                 "agent_analysis": False})
        missing = sorted(requested - set(returned))
        duplicates = parsed["duplicates"] if parsed else []
        absent = {r["ticker"]: r["absent_fields"] for r in observations if r["absent_fields"]}
        governed_obs = [r for r in observations if r["governed"]]
        current = bool(governed_obs) and all(r["freshness"] == "CURRENT" for r in governed_obs)
        fresh = "CURRENT" if current else "STALE" if any(r["freshness"] == "STALE" for r in governed_obs) else "UNVERIFIED"
        governed_defects = set(duplicates) & requested or set(absent) & requested
        coverage = "COMPLETE" if not missing and not governed_defects and parsed and not parsed["partial_response"] else "PARTIAL"
        provider = request["provider"]
        delivery = FEEDS[provider][request["feed"]]
        delay = parsed["provider_reported_delay"] if parsed else None
        if (status == "DELAYED" or (type(delay) in (int, float) and delay > 0)) and delivery == "REAL_TIME":
            failure = "FEED_CONTRADICTION"
        if failure != "NONE":
            cost_state = "UNVERIFIED"
        if provider == "YAHOO":
            coverage = "DISCOVERY_ONLY"
        admissible = (failure == "NONE" and fresh == "CURRENT" and coverage == "COMPLETE"
                      and delivery != "UNAVAILABLE")
        result = {
            "schema": SCHEMA, "provider": provider, "role": PROVIDER_ROLES[provider],
            "adapter_version": ADAPTER_VERSION, "endpoint_class": request["endpoint"],
            "request_identity": expected_request, "request_id": request["request_id"],
            "parents": {**self._parents, "request": expected_request},
            "governed_universe_identity": self._parents["universe"],
            "governed_universe_size": len(self._universe["symbols"]),
            "requested_symbols": sorted(requested), "requested_symbol_hash": content_hash(sorted(requested)),
            "symbols_requested": None if request["mode"] == "FULL_MARKET" or provider == "YAHOO" else len(requested),
            "request_scope": "SCREENER_DISCOVERY" if provider == "YAHOO" else request["mode"],
            "returned_symbols": returned, "returned_symbol_hash": content_hash(returned),
            "symbols_returned": len(all_obs), "distinct_symbols_observed": len(returned),
            "missing_symbols": missing, "unexpected_symbols": unexpected, "duplicate_symbols": duplicates,
            "field_absence": absent, "partial_response": parsed["partial_response"] if parsed else True,
            "provider_event_timestamps": [r["provider_event_timestamps"] for r in observations],
            "request_start": start, "request_end": end, "receipt_time": end,
            "feed_identity": request["feed"], "tier_identity": entry.get("tier_identity", "UNVERIFIED"),
            "delay_classification": delivery, "provider_reported_delay": delay, "response_status": status,
            "raw_response_content_hash": raw_hash, "normalized_observation_hash": content_hash(observations),
            "observations": observations, "freshness": fresh, "coverage": coverage,
            "provenance": "VERIFIED_OFFLINE" if parsed else "UNVERIFIED",
            "admissibility": "ADMISSIBLE_OFFLINE" if admissible else "BLOCKED",
            "entitlement_state": entry["entitlement"],
            "cost_credit_state": cost_state,
            "retry_count": 0, "request_count": 1, "failure_ambiguity": failure,
            "atomic_exchange_snapshot": False, "official_auction_price_proven": False,
            "authority": locked_authority(), "runtime_integration": "NOT_QUALIFIED",
        }
        return seal(result)


def governed_flow(receipts, *, expected_receipts, expected_parents, promotion, expected_promotion, stages):
    """Offline stage evaluation. All effects and any order rail remain absent."""
    stage_rows = []
    reason = None
    if len(receipts) != len(expected_receipts) or len(receipts) != len(expected_parents) or not receipts:
        reason = "INCOMPLETE_EVIDENCE_LINEAGE"
    else:
        try:
            for receipt, expected, parents in zip(receipts, expected_receipts, expected_parents):
                verify_receipt(receipt, expected, parents=parents)
                if (receipt["admissibility"] != "ADMISSIBLE_OFFLINE" or receipt["freshness"] != "CURRENT"
                        or receipt["provenance"] != "VERIFIED_OFFLINE"):
                    raise ValueError("INADMISSIBLE_EVIDENCE")
            # Research/enrichment/discovery cannot replace primary Alpaca SIP truth.
            primary = [r for r in receipts if r["provider"] == "ALPACA" and r["feed_identity"] == "sip"
                       and r["delay_classification"] == "REAL_TIME"]
            if not primary:
                raise ValueError("PRIMARY_SIP_EVIDENCE_REQUIRED")
            safe_document(promotion)
            pin(promotion, expected_promotion)
            if promotion.get("evidence_hashes") != expected_receipts or promotion.get("status") != "PROMOTED":
                raise ValueError("PROMOTION_LINEAGE_INVALID")
            chosen = symbols(promotion.get("symbols"))
            if not set(chosen) <= set(primary[0]["returned_symbols"]) - set(primary[0]["unexpected_symbols"]):
                raise ValueError("PROMOTED_SYMBOL_NOT_OBSERVED")
        except (ValueError, KeyError, TypeError):
            reason = "EVIDENCE_OR_PROMOTION_BLOCKED"
    selected = [] if reason else [r for receipt in receipts for r in receipt["observations"]
                                  if r["ticker"] in chosen and r["governed"]]
    # Preserve disagreements without averaging or substituting provider truth.
    comparisons = {}
    for receipt in receipts:
        for row in receipt.get("observations", []):
            if row.get("governed"):
                comparisons.setdefault(row["ticker"], []).append({"provider": receipt["provider"], "fields": row["fields"]})
    disagreements = {s: rows for s, rows in comparisons.items()
                     if len({content_hash(row["fields"]) for row in rows}) > 1}
    parent = content_hash(expected_receipts)
    for index, name in enumerate(STAGES):
        if reason and index > 0:
            status = "NOT_RUN"
        elif reason:
            status = "BLOCKED"
        elif name in ("GOVERNED_EVIDENCE", "CANDIDATES"):
            status = "PASS"
        elif name == "ALPACA_PAPER_DECISION":
            status = "NO_EXECUTION_OFFLINE"
        elif name in ("RECEIPT", "OUTCOME_LEARNING"):
            status = "RECORDED_OFFLINE" if name == "RECEIPT" else "NOT_RUN_NO_EXECUTION_OUTCOME"
        else:
            callback = stages.get(name)
            if not callable(callback):
                status, reason = "BLOCKED", "STAGE_NOT_CONFIGURED"
            else:
                # Only promoted observations; callbacks do not receive gateway or transport.
                import copy
                try:
                    answer = callback(copy.deepcopy(selected), parent)
                    status = "PASS" if answer == {"status": "PASS", "parent": parent} else "FAIL"
                except Exception:
                    status = "FAIL"
                if status != "PASS":
                    reason = "STAGE_FAILED"
        row = seal({"stage": name, "status": status, "parent": parent})
        stage_rows.append(row)
        parent = content_hash(row)
    return seal({"schema": "iios-provider-offline-flow-v1", "stages": stage_rows,
                 "receipt_parents": expected_receipts, "promotion_parent": expected_promotion,
                 "disagreements": disagreements, "blocked": reason,
                 "authority": locked_authority(), "order_submitted": False,
                 "outcome_learning": "NO_EXECUTION_OUTCOME", "scope": "OFFLINE_ONLY"})
