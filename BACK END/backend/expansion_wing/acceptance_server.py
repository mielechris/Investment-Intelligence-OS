from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from .candidate_enrichment_bridge import validate_browser_projection as validate_enrichment_projection
from .knowledge_pipeline import room_projection
from .multi_asset_projection import SCHEMA_VERSION as MULTI_ASSET_SCHEMA, validate_projection

TELEMETRY_SCHEMA = "batch9g-factory-telemetry-v2"
VALIDATION_SCHEMA = "batch9h-remote-market-validation-v1"
SHADOW_SCHEMA = "batch9i-browser-shadow-strategy-v1"
OUTCOME_SCHEMA = "batch9j-browser-outcome-summary-v1"
ROOMS = [
    "Interview Studio", "Investor Archive", "Philosophy Arena", "Judgment Foundry",
    "Pattern Laboratory", "Strictness Observatory", "Cross-Asset Observatory", "Regime Chamber",
    "Tactical Book", "Strategic Book", "Capital Allocation Room", "Failure Museum",
    "Resource Governor", "Learning Theater",
]


def _valid_origin(value: str) -> bool:
    return value.startswith("http://127.0.0.1:") and value.removeprefix("http://127.0.0.1:").isdigit()


def _read(path: Path, schema: str) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) and value.get("schema_version") == schema else None
    except (OSError, json.JSONDecodeError):
        return None


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _state(observed: Any, *, complete: bool = True, freshness: int = 900) -> str:
    if not complete:
        return "INCOMPLETE"
    parsed = _parse_time(observed)
    if parsed is None:
        return "UNKNOWN"
    return "STALE" if (datetime.now(timezone.utc) - parsed).total_seconds() > freshness else "CURRENT"


def _section(state: str, data: dict[str, Any] | None) -> dict[str, Any]:
    return {"state": state, "data": data}


def _safe_scoreboard(value: Any) -> dict[str, Any] | None:
    fields = {"observations_evaluated", "unresolved_observations", "hit_rate", "return_distribution",
        "drawdown_distribution", "calibration", "average_disclosure_delay_seconds", "evidence_completeness",
        "regime_dependence", "sample_size_warning", "survivorship_bias_warning", "look_ahead_permitted",
        "investment_endorsement"}
    if not isinstance(value, dict) or set(value) != fields or any(isinstance(item, (dict, list)) for item in value.values()):
        return None
    if value.get("investment_endorsement") is not False or value.get("look_ahead_permitted") is not False:
        return None
    return {key: value[key] for key in sorted(fields)}


def _safe_authority(payload: dict[str, Any], *, telemetry: bool = False) -> bool:
    safety = payload.get("safety")
    if not isinstance(safety, dict):
        return False
    false_keys = ("broker_connected", "trade_execution_permission", "live_execution")
    if any(safety.get(key) is not False for key in false_keys):
        return False
    return not telemetry or safety.get("telemetry_read_only") is True


def _safe_outcome(payload: dict[str, Any]) -> bool:
    safety = payload.get("safety")
    return isinstance(safety, dict) and safety.get("read_only_browser_payload") is True and all(
        safety.get(key) is False for key in ("auto_write_judgment_bank", "trade_execution_permission", "live_execution"))


def _confidence(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "UNKNOWN"
    if value >= 0.8: return "HIGH"
    if value >= 0.5: return "MEDIUM"
    return "LOW"


def _passports(telemetry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = telemetry.get("recent_promotions")
    if not isinstance(rows, list):
        return []
    output = []
    for row in rows[:20]:
        if not isinstance(row, dict): continue
        candidate = row.get("source_candidate_id") or row.get("case_id")
        ticker = row.get("ticker")
        if not isinstance(candidate, str) or not candidate or not isinstance(ticker, str) or not ticker:
            continue
        committee = row.get("committee") if isinstance(row.get("committee"), dict) else {}
        risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
        committee_status = str(committee.get("disposition") or "UNKNOWN")[:40]
        risk_status = str(risk.get("decision") or "UNKNOWN")[:40]
        output.append({
            "candidate_id": "candidate_" + hashlib.sha256(candidate.encode()).hexdigest()[:16],
            "instrument": ticker[:20], "asset_class": "EQUITY", "discovered_at": row.get("promoted_at"),
            "source_category": "SANITIZED_RADAR_PROMOTION", "governed_stage": "PROMOTED_CASE",
            "classification": "OBSERVATION_ONLY", "freshness": _state(row.get("promoted_at"), freshness=86_400),
            "confidence_category": _confidence(committee.get("confidence")), "missing_evidence_categories": [],
            "committee_status": committee_status, "risk_status": risk_status,
            "paper_eligibility_status": "NOT_AUTHORIZED",
            "rejection_category": "OBSERVATION_ONLY_BOUNDARY",
            "authority": {"paper_order": False, "automatic_promotion": False, "broker": False, "live_execution": False},
        })
    return output


class Compositor:
    def __init__(self, telemetry: Path, validation: Path, shadow: Path, outcome: Path, backend: str,
                 knowledge_reader: Callable[[], dict[str, Any]] | None = None,
                 enrichment_reader: Callable[[], dict[str, Any]] | None = None,
                 multi_asset_reader: Callable[[], dict[str, Any]] | None = None) -> None:
        self.paths = telemetry, validation, shadow, outcome
        self.backend = backend
        self.snapshot_requests = 0
        self.backend_requests = 0
        self.backend_latencies_ms: list[float] = []
        self.backend_errors: dict[str, int] = {}
        self.knowledge_reader = knowledge_reader
        self.enrichment_reader = enrichment_reader
        self.multi_asset_reader = multi_asset_reader

    def _reachability(self) -> str:
        self.backend_requests += 1
        started = time.perf_counter()
        try:
            request = Request(self.backend, method="GET", headers={"Accept": "application/json"})
            with urlopen(request, timeout=2.0) as response:
                if response.status != 200:
                    raise RuntimeError("HTTP_STATUS")
                json.loads(response.read(200_000))
            return "CURRENT"
        except Exception as exc:
            category = type(exc).__name__[:40]
            self.backend_errors[category] = self.backend_errors.get(category, 0) + 1
            return "UNAVAILABLE"
        finally:
            self.backend_latencies_ms.append(round((time.perf_counter() - started) * 1000, 3))

    def snapshot(self) -> dict[str, Any]:
        self.snapshot_requests += 1
        telemetry = _read(self.paths[0], TELEMETRY_SCHEMA)
        validation = _read(self.paths[1], VALIDATION_SCHEMA)
        shadow = _read(self.paths[2], SHADOW_SCHEMA)
        outcome = _read(self.paths[3], OUTCOME_SCHEMA)
        sections: dict[str, Any] = {}
        backend_state = self._reachability()
        if telemetry and _safe_authority(telemetry, telemetry=True):
            generated = telemetry.get("generated_at")
            cadence = telemetry.get("cadence") if isinstance(telemetry.get("cadence"), dict) else {}
            observation = cadence.get("observation") if isinstance(cadence.get("observation"), dict) else {}
            paper = cadence.get("paper_trading") if isinstance(cadence.get("paper_trading"), dict) else {}
            radar = telemetry.get("radar") if isinstance(telemetry.get("radar"), dict) else {}
            fund = telemetry.get("paper_fund") if isinstance(telemetry.get("paper_fund"), dict) else {}
            state = _state(generated)
            sections["service_health"] = _section(state if backend_state == "CURRENT" else "UNAVAILABLE", {
                "backend_reachable": backend_state == "CURRENT", "observation_status": observation.get("status") or "UNKNOWN"})
            sections["last_cycle"] = _section(state, {"paper_trading_status": paper.get("status") or "UNKNOWN"})
            sections["radar"] = _section(_state(radar.get("last_cycle_completed_at")), {
                "governed_universe_count": radar.get("governed_universe_count"),
                "screener_hit_count": radar.get("screener_hit_count"),
                "promotion_candidate_count": radar.get("promotion_candidate_count"),
                "promoted_case_count": radar.get("promoted_case_count"),
                "candidate_lineage_state": radar.get("candidate_lineage_state") or "UNAVAILABLE",
                "candidate_lineage_reason": radar.get("candidate_lineage_reason"),
                "candidate_source_cycle_id": radar.get("candidate_source_cycle_id"),
                "candidate_source_artifact_hash": radar.get("candidate_source_artifact_hash")})
            candidate_batch = radar.get("candidate_batch") if isinstance(radar.get("candidate_batch"), dict) else None
            candidate_rows = candidate_batch.get("candidates") if candidate_batch else None
            lineage_state = str(radar.get("candidate_lineage_state") or "UNAVAILABLE")
            if not isinstance(candidate_rows, list) or len(candidate_rows) > 5:
                candidate_rows = []
                if lineage_state != "AVAILABLE_EMPTY": lineage_state = "UNAVAILABLE"
            safe_rows = []
            for row in candidate_rows:
                if not isinstance(row, dict) or set(row) != {"candidate_id", "ticker", "discovered_at", "missing_fields"}:
                    lineage_state = "UNAVAILABLE"; safe_rows = []; break
                safe_rows.append({key: row[key] for key in ("candidate_id", "ticker", "discovered_at", "missing_fields")})
            sections["candidate_conveyor"] = _section(lineage_state, {
                "route": ["9E", "PRIMARY REVIEW", "CASE DRAFT"], "candidates": safe_rows,
                "candidate_count": len(safe_rows), "automatic_promotion": False,
                "paper_order": False, "broker": False, "live_execution": False})
            sections["post_close_control"] = _section("WAITING", {"automatic_schedule": False})
            sections["governed_cases"] = _section("AWAITING", {"case_draft_count": 0, "automatic_promotion": False})
            sections["primary_source_review_queue"] = _section(
                "AWAITING" if safe_rows else ("AVAILABLE_EMPTY" if lineage_state == "AVAILABLE_EMPTY" else "UNAVAILABLE"),
                {"queue_count": len(safe_rows), "human_review_required": True})
            sections["provider_credit_meter"] = _section("UNAVAILABLE", {
                "provider_enabled": False, "credits_consumed_by_preview": 0})
            passports = _passports(telemetry)
            sections["radar"]["data"]["opportunity_passports"] = passports
            sections["radar"]["data"]["passport_status"] = "CURRENT" if passports else "AVAILABLE_EMPTY"
            positions = fund.get("position_count") if isinstance(fund.get("position_count"), int) else None
            transactions = fund.get("transaction_count") if isinstance(fund.get("transaction_count"), int) else None
            orders = len(telemetry.get("recent_paper_orders")) if isinstance(telemetry.get("recent_paper_orders"), list) else None
            fills = len(telemetry.get("recent_paper_fills")) if isinstance(telemetry.get("recent_paper_fills"), list) else None
            sections["books"] = _section(_state(fund.get("snapshot_as_of")), {
                "nav": fund.get("nav"), "cash": fund.get("cash"), "positions": positions,
                "transactions": transactions, "orders": orders, "fills": fills,
                "tactical": {"allocation_capacity": 3000, "invested_capital_claimed": False},
                "strategic": {"allocation_capacity": 5000, "invested_capital_claimed": False},
                "reserve": {"allocation_capacity": 2000, "invested_capital_claimed": False}})
        else:
            for key in ("service_health", "last_cycle", "radar", "books", "candidate_conveyor",
                        "post_close_control", "governed_cases", "primary_source_review_queue",
                        "provider_credit_meter"):
                sections[key] = _section("UNAVAILABLE", None)
        if validation:
            complete = validation.get("benchmark_complete") is True
            metrics = validation.get("metrics") if isinstance(validation.get("metrics"), dict) else {}
            sections["benchmark_9h"] = _section(_state(validation.get("generated_at"), complete=complete, freshness=86_400), {
                "benchmark_complete": complete, "status": validation.get("status") or "UNKNOWN",
                "opportunity_count": metrics.get("opportunity_count"), "detected_count": metrics.get("detected_count"),
                "missed_count": metrics.get("missed_count")})
        else:
            sections["benchmark_9h"] = _section("UNAVAILABLE", None)
        if shadow and all(shadow.get(key) is False for key in (
            "automatic_threshold_changes", "automatic_weight_changes", "judgment_bank_auto_write",
            "ledger_write", "trade_execution_permission", "broker_connected", "live_execution")):
            sections["shadow_9i"] = _section(str(shadow.get("truth_state") or "UNKNOWN"), {
                key: shadow.get(key) for key in ("status", "complete_sessions", "required_sessions", "maturity_state",
                    "five_session_mature_count", "advice_issued", "observational_only", "automatic_threshold_changes",
                    "automatic_weight_changes", "judgment_bank_auto_write", "ledger_read", "ledger_write",
                    "trade_execution_permission", "broker_connected", "live_execution", "reason")})
        else:
            sections["shadow_9i"] = _section("UNAVAILABLE", {"truth_state": "UNAVAILABLE", "reason": "BROWSER_SUMMARY_NOT_AVAILABLE"})
        if outcome and _safe_outcome(outcome):
            safety = outcome.get("safety") if isinstance(outcome.get("safety"), dict) else {}
            sections["outcomes_9j"] = _section(_state(outcome.get("generated_at"), freshness=86_400), {
                "status": outcome.get("status") or "UNKNOWN", "complete_session_count": outcome.get("complete_session_count"),
                "outcome_count": outcome.get("outcome_count"), "mature_5d_count": outcome.get("mature_5d_count"),
                "pending_5d_count": outcome.get("pending_5d_count"),
                "auto_write_judgment_bank": safety.get("auto_write_judgment_bank") is True,
                "trade_execution_permission": safety.get("trade_execution_permission") is True,
                "live_execution": safety.get("live_execution") is True})
        else:
            sections["outcomes_9j"] = _section("UNAVAILABLE", None)
        for key in ("cases", "committee", "risk", "resources", "queue"):
            sections[key] = _section("UNAVAILABLE", None)
        validation_state = sections["benchmark_9h"]["state"]
        room_states = room_projection()
        room_states["Interview Studio"]["data"].update({
                "reviewed_upload_intake": "AVAILABLE_FOR_REVIEWED_UPLOAD", "active_interviews_claimed": False,
                "consent_required": True, "human_approval_required": True})
        room_states["Investor Archive"]["data"]["durable_store"] = "NOT_ACTIVATED"
        room_states.update({
            "Strictness Observatory": {"state": validation_state, "presentation_status": validation_state, "data": {
                "policies": ["CURRENT", "BALANCED", "EXPLORATORY"], "simulation_only": True,
                "performance_calculated": False, "evidence_state": validation_state}},
            "Strategy Incubator": {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                "eligible_strategy_count": 0, "observation_only": True, "automatic_promotion": False}},
            "Learning Theater": {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                "limits": {"max_cpu_pct": 60, "max_memory_mb": 2048, "max_concurrent_ai_tasks": 2,
                    "provider_requests_per_day": 100, "provider_cost_per_day": 10, "max_queue_depth": 200},
                "usage_measured": False, "queue_count": None, "raw_tasks_exposed": False}},
            "Resource Governor": {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                "acquisition_scheduled": False, "network_enabled": False, "provider_enabled": False,
                "cost_usd": 0, "authority_granted": False}},
        })
        if self.knowledge_reader is not None:
            try: knowledge = self.knowledge_reader()
            except Exception: knowledge = None
            if isinstance(knowledge, dict):
                sections["knowledge_operations"] = _section("CURRENT", knowledge)
                counts = {key: knowledge.get(key, 0) for key in ("source_count", "note_count", "claim_count",
                    "rights_review_queue_count", "transcript_review_queue_count", "contradiction_queue_count",
                    "judgment_queue_count", "pattern_queue_count")}
                room_states["Interview Studio"] = {"state": "CURRENT", "presentation_status": "NOT_ACTIVATED", "data": {
                    "transcription": knowledge.get("transcription"), "review_service": knowledge.get("review_service"),
                    "transcript_review_queue_count": counts["transcript_review_queue_count"]}}
                room_states["Investor Archive"] = {"state": "CURRENT", "presentation_status": knowledge.get("archive"), "data": {
                    "source_count": counts["source_count"], "note_count": counts["note_count"],
                    "claim_count": counts["claim_count"], "rights_review_queue_count": counts["rights_review_queue_count"],
                    "public_source_intake": knowledge.get("public_source_intake")}}
                room_states["Philosophy Arena"] = {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                    "contradiction_queue_count": counts["contradiction_queue_count"], "completed_intelligence_claimed": False}}
                room_states["Judgment Foundry"] = {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                    "judgment_queue_count": counts["judgment_queue_count"], "validated_judgment_count": 0}}
                room_states["Pattern Laboratory"] = {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                    "pattern_queue_count": counts["pattern_queue_count"], "validated_pattern_count": 0}}
                room_states["Learning Theater"] = {"state": "CURRENT", "presentation_status": "READY", "data": {
                    "operational_encryption": knowledge.get("operational_encryption"), "keychain": knowledge.get("keychain"),
                    "backup_recovery": knowledge.get("backup_recovery"), "owner_reviewer": knowledge.get("owner_reviewer"),
                    "review_service": knowledge.get("review_service"), "private_data_exposed": False}}
                room_states["Resource Governor"] = {"state": "CURRENT", "presentation_status": "AVAILABLE_EMPTY", "data": {
                    "acquisition_scheduled": False, "network_enabled": False, "provider_enabled": False,
                    "cost_usd": 0, "authority_granted": False}}
            else:
                sections["knowledge_operations"] = _section("UNAVAILABLE", None)
        if self.enrichment_reader is not None:
            try:
                enrichment = self.enrichment_reader()
                validate_enrichment_projection(enrichment)
            except Exception:
                enrichment = None
            if enrichment is None:
                sections["candidate_enrichment"] = _section("UNAVAILABLE", None)
            else:
                sections["candidate_enrichment"] = _section("CURRENT", enrichment)
                room_states["Resource Governor"] = {"state": "CURRENT",
                    "presentation_status": "READY" if enrichment["candidate_count"] else "AVAILABLE_EMPTY",
                    "data": {"candidate_count": enrichment["candidate_count"],
                        "unique_ticker_count": enrichment["unique_ticker_count"],
                        "provider_request_count": enrichment["provider_request_count"],
                        "cache_hit_count": enrichment["cache_hit_count"],
                        "new_conservative_credits": enrichment["new_conservative_credits"],
                        "primary_review_queue_count": enrichment["primary_review_queue_count"],
                        "network_enabled": False, "provider_enabled": False, "authority_granted": False}}
        if self.multi_asset_reader is not None:
            try: multi_asset = self.multi_asset_reader()
            except Exception: multi_asset = None
            safe_states = {"AVAILABLE", "AVAILABLE_EMPTY", "STALE", "INCOMPLETE", "UNAVAILABLE", "FAILED_CLOSED"}
            if isinstance(multi_asset, dict) and multi_asset.get("schema_version") == MULTI_ASSET_SCHEMA:
                try: validate_projection(multi_asset)
                except ValueError: multi_asset = None
                if multi_asset is not None:
                    lanes = multi_asset["lane_states"]
                    conveyor = multi_asset["candidate_conveyor"]
                    sections["multi_asset_factory"] = _section(conveyor["state"], {
                        "market_session_state": multi_asset["market_session_state"],
                        "projection_freshness": multi_asset["evidence_freshness_state"],
                        "source_cycle_id": multi_asset["source_cycle_id"], "lane_states": lanes,
                        "candidates": conveyor["candidates"], "provider": multi_asset["provider"],
                        "queue": multi_asset["queue"], "consolidated_paper_nav": multi_asset["consolidated_paper_nav"],
                        "authority_locked": True})
                    sections["candidate_conveyor"] = _section(conveyor["state"], {
                        "route": ["9E", "PRIMARY REVIEW", "CASE DRAFT"],
                        "candidates": conveyor["candidates"], "source_cycle_id": multi_asset["source_cycle_id"],
                        "automatic_promotion": False, "paper_order": False, "broker": False,
                        "live_execution": False})
                    sections["provider_credit_meter"] = _section(
                        multi_asset["provider"]["state"], multi_asset["provider"])
                    sections["professional_strategy_observatory"] = _section(
                        multi_asset["professional_observatory"]["state"], multi_asset["professional_observatory"])
                    sections["method_manager_scoreboard"] = _section(
                        multi_asset["scoreboard"]["state"], multi_asset["scoreboard"])
                    sections["paper_research_sleeves"] = _section(
                        multi_asset["paper_research_sleeves"]["state"], multi_asset["paper_research_sleeves"])
                    sections["market_session"] = _section("AVAILABLE", {
                        "state": multi_asset["market_session_state"], "source_generated_at": multi_asset["source_generated_at"],
                        "projection_generated_at": multi_asset["projection_generated_at"]})
                    sections["projection_freshness"] = _section(
                        multi_asset["evidence_freshness_state"], {"last_trustworthy_hash": multi_asset["last_trustworthy_hash"]})
                    sections["authority_lock"] = _section("AVAILABLE", {
                        "locked": True, "provider": False, "credential": False, "paper_order": False,
                        "ledger_write": False, "broker": False, "live_execution": False})
            if all(key in sections for key in ("multi_asset_factory", "professional_strategy_observatory",
                                                "method_manager_scoreboard", "paper_research_sleeves")):
                multi_asset = None
            if multi_asset is None and "multi_asset_factory" in sections:
                pass
            else:
                safe_authority = isinstance(multi_asset, dict) and isinstance(multi_asset.get("authority"), dict) and not any(multi_asset["authority"].values())
                lanes = multi_asset.get("lane_states") if isinstance(multi_asset, dict) else None
                scoreboard = _safe_scoreboard(multi_asset.get("scoreboard")) if isinstance(multi_asset, dict) else None
                if (safe_authority and isinstance(lanes, dict) and len(lanes) == 10 and
                        all(isinstance(k, str) and v in safe_states for k, v in lanes.items()) and
                        multi_asset.get("consolidated_paper_nav") == 10_000 and scoreboard is not None):
                    sections["multi_asset_factory"] = _section(str(multi_asset.get("state") or "UNKNOWN"), {
                    "lane_states": lanes, "professional_observation_count": multi_asset.get("professional_observation_count", 0),
                    "paper_sleeve_count": multi_asset.get("paper_sleeve_count", 0),
                    "consolidated_paper_nav": 10_000, "provider_status": multi_asset.get("provider_status"),
                    "queue_depth": multi_asset.get("queue_depth", 0), "last_successful_cycle": multi_asset.get("last_successful_cycle"),
                    "failure_reasons": multi_asset.get("failure_reasons", []), "research_only": True})
                    sections["professional_strategy_observatory"] = _section(
                    "AVAILABLE_EMPTY" if multi_asset.get("professional_observation_count", 0) == 0 else "CURRENT",
                    {"observation_count": multi_asset.get("professional_observation_count", 0),
                     "investment_endorsement": False, "automatic_promotion": False})
                    sections["method_manager_scoreboard"] = _section("INCOMPLETE", scoreboard)
                    sections["paper_research_sleeves"] = _section(
                    "AVAILABLE_EMPTY" if multi_asset.get("paper_sleeve_count", 0) == 0 else "CURRENT",
                    {"sleeve_count": multi_asset.get("paper_sleeve_count", 0), "consolidated_paper_nav": 10_000,
                     "paper_positions_inferred": False})
                else:
                    for key in ("multi_asset_factory", "professional_strategy_observatory",
                                "method_manager_scoreboard", "paper_research_sleeves"):
                        sections[key] = _section("UNAVAILABLE", None)
        else:
            for key in ("multi_asset_factory", "professional_strategy_observatory",
                        "method_manager_scoreboard", "paper_research_sleeves"):
                sections[key] = _section("UNAVAILABLE", None)
        section_rooms = {"Cross-Asset Observatory": "radar", "Regime Chamber": "last_cycle", "Tactical Book": "books",
            "Strategic Book": "books", "Capital Allocation Room": "books", "Failure Museum": "benchmark_9h"}
        for room, key in section_rooms.items():
            room_states[room] = {"state": sections[key]["state"], "presentation_status": sections[key]["state"],
                                 "data": sections[key]["data"]}
        return {"schema_version": "expansion-wing-truth-v1", "mode": "READ_ONLY", "sections": sections,
                "room_states": room_states,
                "rooms": ROOMS, "fabricated_activity": False,
                "authority": {"paper_mode": True, "credential_access": False, "ledger_write_authority": False,
                    "broker_connectivity": False, "live_execution_authority": False}}

    def metrics(self) -> dict[str, Any]:
        return {"snapshot_requests": self.snapshot_requests, "backend_requests": self.backend_requests,
                "backend_latencies_ms": self.backend_latencies_ms[-100:], "backend_errors": self.backend_errors}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--telemetry", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--shadow", required=True, type=Path)
    parser.add_argument("--outcome", required=True, type=Path)
    parser.add_argument("--backend", default="http://127.0.0.1:8002/system/status")
    parser.add_argument("--allowed-origin", required=True)
    args = parser.parse_args()
    if not _valid_origin(args.allowed_origin):
        parser.error("--allowed-origin must be an exact 127.0.0.1 HTTP origin")
    compositor = Compositor(args.telemetry, args.validation, args.shadow, args.outcome, args.backend)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", args.allowed_origin)
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/snapshot": self._send(compositor.snapshot())
            elif self.path == "/metrics": self._send(compositor.metrics())
            else: self._send({"status": "NOT_FOUND"}, 404)

        def __getattr__(self, name: str):
            if name.startswith("do_"):
                return lambda: self._send({"status": "METHOD_NOT_ALLOWED"}, 405)
            raise AttributeError(name)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
