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

from .knowledge_pipeline import room_projection

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
                 knowledge_reader: Callable[[], dict[str, Any]] | None = None) -> None:
        self.paths = telemetry, validation, shadow, outcome
        self.backend = backend
        self.snapshot_requests = 0
        self.backend_requests = 0
        self.backend_latencies_ms: list[float] = []
        self.backend_errors: dict[str, int] = {}
        self.knowledge_reader = knowledge_reader

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
                "promoted_case_count": radar.get("promoted_case_count")})
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
            for key in ("service_health", "last_cycle", "radar", "books"):
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
