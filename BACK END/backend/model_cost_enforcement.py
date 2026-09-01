from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import fcntl

SCHEMA_VERSION = "batch10m-grok-cost-enforcement-v1"
DEFAULT_COST_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "model-cost"
LEDGER_NAME = "model_usage.jsonl"
ADMISSION_LEDGER_NAME = "admission_events.jsonl"
ARTIFACT_NAME = "latest_model_cost_governor.json"
HOOK_REGISTRY_NAME = "enforcement_hooks.json"
RESERVATION_NAME = "active_reservations.json"
INTEGRITY_NAME = "budget_integrity.json"
LOCK_NAME = ".model-cost.lock"
LOCK_TIMEOUT_SECONDS = 2.0
_PROCESS_LOCK = threading.RLock()
USD_TICKS_PER_USD = 10_000_000_000

POLICY = {
    "daily_soft_limit_ticks": 100_000_000_000,
    "daily_hard_limit_ticks": 200_000_000_000,
    "rolling_7d_soft_limit_ticks": 500_000_000_000,
    "rolling_7d_hard_limit_ticks": 750_000_000_000,
    "max_expensive_requests_per_case": 8,
    "max_estimated_input_tokens_per_request": 16000,
    "max_expensive_calls_per_hour": 20,
    "max_x_search_tool_calls_per_request": 3,
    "duplicate_query_ttl_seconds": 1800,
    "max_output_tokens_per_request": 2000,
    "pricing_model": "grok-4.6",
    "pricing_verified": False,
    "pricing_source_name": "",
    "pricing_source_reference": "",
    "pricing_verified_date": "",
    "pricing_verifier_id": "",
    "pricing_expires_date": "",
    "pricing_max_age_days": 90,
    "input_ticks_per_million_tokens": 20_000_000_000,
    "output_ticks_per_million_tokens": 100_000_000_000,
    "x_search_ticks_per_call": 500_000_000,
    "reservation_safety_margin_numerator": 125,
    "reservation_safety_margin_denominator": 100,
    "currency": "USD",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cost_dir() -> Path:
    return DEFAULT_COST_DIR


def max_x_search_tool_calls() -> int:
    return int(POLICY["max_x_search_tool_calls_per_request"])


def max_output_tokens() -> int:
    return int(POLICY["max_output_tokens_per_request"])


def _required_positive_int(name: str) -> int:
    value = POLICY.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError("Grok pricing policy is invalid; request denied")
    return value


def maximum_request_reservation_ticks(*, model: str) -> int:
    provenance = ("pricing_source_name", "pricing_source_reference", "pricing_verified_date", "pricing_verifier_id", "pricing_expires_date")
    if POLICY.get("pricing_verified") is not True or any(not isinstance(POLICY.get(field), str) or not POLICY[field].strip() or POLICY[field].strip().lower() in {"todo", "placeholder", "unverified"} for field in provenance):
        raise RuntimeError("Grok pricing is unverified; request denied")
    if model != str(POLICY.get("pricing_model") or ""):
        raise RuntimeError("Grok pricing policy has no matching model; request denied")
    try:
        effective_date = datetime.fromisoformat(str(POLICY["pricing_verified_date"])).date()
        expires_date = datetime.fromisoformat(str(POLICY["pricing_expires_date"])).date()
        max_age_days = int(POLICY["pricing_max_age_days"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Grok pricing policy is invalid; request denied") from exc
    if POLICY.get("currency") != "USD" or max_age_days < 1 or (_utc_now().date() - effective_date).days > max_age_days or _utc_now().date() > expires_date:
        raise RuntimeError("Grok pricing policy is stale; request denied")
    input_limit = int(POLICY["max_estimated_input_tokens_per_request"])
    output_limit = int(POLICY["max_output_tokens_per_request"])
    tool_limit = max_x_search_tool_calls()
    if input_limit < 1 or output_limit < 1 or tool_limit < 1:
        raise RuntimeError("Grok request limits are invalid; request denied")
    base = (
        input_limit * _required_positive_int("input_ticks_per_million_tokens") // 1_000_000
        + output_limit * _required_positive_int("output_ticks_per_million_tokens") // 1_000_000
        + tool_limit * _required_positive_int("x_search_ticks_per_call")
    )
    return (base * _required_positive_int("reservation_safety_margin_numerator") + _required_positive_int("reservation_safety_margin_denominator") - 1) // _required_positive_int("reservation_safety_margin_denominator")


def _safe_cost_dir() -> Path:
    path = _cost_dir()
    approved_root = DEFAULT_COST_DIR.resolve()
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        raise RuntimeError("Grok cost ledger path is unsafe")
    try:
        path.resolve().relative_to(approved_root)
    except ValueError as exc:
        raise RuntimeError("Grok cost ledger path is outside the approved root") from exc
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode)
    if path.is_symlink() or (hasattr(os, "getuid") and path.stat().st_uid != os.getuid()) or mode & 0o077:
        raise RuntimeError("Grok cost ledger path is not owner-private")
    return path


@contextmanager
def _ledger_lock():
    with _PROCESS_LOCK:
        directory = _safe_cost_dir()
        descriptor = os.open(directory / LOCK_NAME, os.O_CREAT | os.O_RDWR, 0o600)
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        acquired = False
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Grok cost ledger lock unavailable; request denied")
                    time.sleep(0.02)
            yield directory
        finally:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def query_fingerprint(query: str | None) -> str | None:
    if not query:
        return None
    normalized = " ".join(str(query).lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def sanitize_error(value: Any) -> str:
    text = str(value or "")
    def redact_url(match: re.Match[str]) -> str:
        parts = urlsplit(match.group(0))
        query = []
        for name, item in parse_qsl(parts.query, keep_blank_values=True):
            sensitive = unquote(name).lower() in {"api_key", "apikey", "token", "secret", "password", "access_token"}
            query.append((name, "[REDACTED]" if sensitive else item))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

    text = re.sub(r"https?://[^\s]+", redact_url, text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)([?&](?:api[_-]?key|token|secret|password|access_token)=)[^&#\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(?:xai-|sk-|AIza)[A-Za-z0-9._-]{8,}", "[REDACTED]", text)
    text = re.sub(r"https?://([^/@\s]+)@", "https://[REDACTED]@", text)
    return text[:500]


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        payload = (json.dumps(row, sort_keys=True, default=str) + "\n").encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_reservations(directory: Path) -> list[dict[str, Any]]:
    path = directory / RESERVATION_NAME
    if not path.exists():
        return []
    if path.is_symlink():
        raise RuntimeError("Grok cost reservations are unsafe; request denied")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Grok cost reservations are unreadable; request denied") from exc
    reservations = payload.get("reservations") if isinstance(payload, dict) else None
    if not isinstance(reservations, list):
        raise RuntimeError("Grok cost reservations are malformed; request denied")
    for item in reservations:
        amount = item.get("amount_ticks") if isinstance(item, dict) else None
        if not isinstance(item, dict) or not isinstance(item.get("reservation_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", item["reservation_id"]) or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 or _parse_time(item.get("created_at")) is None:
            raise RuntimeError("Grok cost reservations are malformed; request denied")
    return reservations


def _write_reservations(directory: Path, reservations: list[dict[str, Any]]) -> None:
    path = directory / RESERVATION_NAME
    temporary = directory / (RESERVATION_NAME + ".tmp")
    _atomic_json_write(directory, RESERVATION_NAME, {"reservations": reservations})


def _atomic_json_write(directory: Path, filename: str, payload: dict[str, Any]) -> None:
    temporary = directory / (filename + ".tmp")
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, directory / filename)
    directory_descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _integrity_state(directory: Path) -> dict[str, Any]:
    path = directory / INTEGRITY_NAME
    if not path.exists():
        return {"blocked": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Grok budget integrity state is unreadable; request denied") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("blocked"), bool):
        raise RuntimeError("Grok budget integrity state is malformed; request denied")
    return payload


def _read_events(directory: Path) -> list[dict[str, Any]]:
    path = directory / LEDGER_NAME
    if not path.exists():
        return []
    if path.is_symlink():
        raise RuntimeError("Grok cost ledger is unsafe; request denied")
    output: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError("Grok cost ledger is unreadable; request denied") from exc
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Grok cost ledger is malformed; request denied") from exc
        amount = row.get("cost_ticks") if isinstance(row, dict) else None
        if not isinstance(row, dict) or row.get("event_type") != "SETTLEMENT" or _parse_time(row.get("timestamp")) is None or not isinstance(row.get("reservation_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", row["reservation_id"]) or isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise RuntimeError("Grok cost ledger is malformed; request denied")
        output.append(row)
    return output


def _window(events: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in events:
        timestamp = _parse_time(row.get("timestamp"))
        if timestamp is not None and start <= timestamp <= end:
            selected.append(row)
    return selected


def _sum_exact(events: list[dict[str, Any]]) -> int:
    return sum(row["cost_ticks"] for row in events)


def _current_state(directory: Path, now: datetime | None = None) -> dict[str, Any]:
    now_value = now or _utc_now()
    events = _read_events(directory)
    reservations = _read_reservations(directory)
    today_start = now_value.replace(hour=0, minute=0, second=0, microsecond=0)
    hour_start = now_value - timedelta(hours=1)
    week_start = now_value - timedelta(days=7)
    today = _window(events, today_start, now_value)
    hour = _window(events, hour_start, now_value)
    week = _window(events, week_start, now_value)
    daily = _sum_exact(today)
    weekly = _sum_exact(week)
    return {
        "now": now_value,
        "events": events,
        "today": today,
        "hour": hour,
        "week": week,
        "daily_exact_spend_ticks": daily,
        "weekly_exact_spend_ticks": weekly,
        "active_reservations": reservations,
    }


def _decision_event(directory: Path, decision: dict[str, Any], *, query_fp: str | None, case_id: str | None, model: str, estimated_input_tokens: int) -> None:
    _append_jsonl(
        directory / ADMISSION_LEDGER_NAME,
        {
            "timestamp": _iso(_utc_now()),
            "decision": decision.get("decision"),
            "reasons": list(decision.get("reasons") or []),
            "query_fingerprint": query_fp,
            "case_id": case_id,
            "provider": "XAI",
            "model": model,
            "estimated_input_tokens": max(0, int(estimated_input_tokens or 0)),
            "binding": True,
            "prompt_persisted": False,
            "api_key_persisted": False,
        },
    )


def preflight_xai_request(*, query: str, model: str, case_id: str | None = None, estimated_input_tokens: int = 0) -> dict[str, Any]:
    """Binding admission gate for the Grok/X-search request boundary only."""
    with _ledger_lock() as directory:
        return _preflight_xai_request(directory, query=query, model=model, case_id=case_id, estimated_input_tokens=estimated_input_tokens)


def _preflight_xai_request(directory: Path, *, query: str, model: str, case_id: str | None, estimated_input_tokens: int) -> dict[str, Any]:
    state = _current_state(directory)
    now_value: datetime = state["now"]
    fp = query_fingerprint(query)
    reasons: list[str] = []
    decision = "ALLOW"

    daily = state["daily_exact_spend_ticks"]
    weekly = state["weekly_exact_spend_ticks"]
    reservation_amount = maximum_request_reservation_ticks(model=model)
    reserved = sum(item["amount_ticks"] for item in state["active_reservations"])
    integrity = _integrity_state(directory)
    if integrity["blocked"]:
        decision = "BLOCK_BUDGET_INTEGRITY"
        reasons.append("BUDGET_INTEGRITY_REMEDIATION_REQUIRED")
    elif daily + reserved + reservation_amount > POLICY["daily_hard_limit_ticks"] or weekly + reserved + reservation_amount > POLICY["rolling_7d_hard_limit_ticks"]:
        decision = "BLOCK_HARD_BUDGET"
        reasons.append("COMPLETED_SPEND_AND_RESERVATIONS_WOULD_EXCEED_HARD_LIMIT")
    elif daily >= POLICY["daily_soft_limit_ticks"] or weekly >= POLICY["rolling_7d_soft_limit_ticks"]:
        decision = "DEFER_SOFT_BUDGET"
        reasons.append("EXACT_SPEND_AT_OR_ABOVE_SOFT_LIMIT")

    if estimated_input_tokens > int(POLICY["max_estimated_input_tokens_per_request"]):
        decision = "DEFER_CONTEXT_LIMIT" if decision == "ALLOW" else decision
        reasons.append("ESTIMATED_INPUT_CONTEXT_EXCEEDS_POLICY")

    hour = list(state["hour"])
    if len(hour) >= int(POLICY["max_expensive_calls_per_hour"]):
        decision = "DEFER_HOURLY_LIMIT" if decision == "ALLOW" else decision
        reasons.append("EXPENSIVE_CALLS_AT_HOURLY_LIMIT")

    if case_id:
        case_count = sum(1 for row in hour if str(row.get("case_id") or "") == str(case_id))
        if case_count >= int(POLICY["max_expensive_requests_per_case"]):
            decision = "DEFER_CASE_LIMIT" if decision == "ALLOW" else decision
            reasons.append("CASE_REQUEST_COUNT_AT_POLICY_LIMIT")

    if fp:
        ttl = int(POLICY["duplicate_query_ttl_seconds"])
        for row in reversed(state["events"]):
            if str(row.get("query_fingerprint") or "") != fp:
                continue
            seen = _parse_time(row.get("timestamp"))
            if seen and 0 <= (now_value - seen).total_seconds() <= ttl:
                decision = "DEFER_DUPLICATE" if decision == "ALLOW" else decision
                reasons.append("DUPLICATE_QUERY_INSIDE_TTL")
            break

    result = {
        "decision": decision,
        "allow": decision == "ALLOW",
        "reasons": reasons or ["WITHIN_BINDING_GROK_COST_POLICY"],
        "binding": True,
        "daily_exact_spend_ticks": daily,
        "rolling_7d_exact_spend_ticks": weekly,
        "active_reservations_ticks": reserved,
        "query_fingerprint": fp,
        "policy_version": SCHEMA_VERSION,
        "trade_execution_permission": False,
        "capital_authority": False,
        "live_execution": False,
    }
    if result["allow"]:
        reservation_id = uuid.uuid4().hex
        state["active_reservations"].append({"reservation_id": reservation_id, "amount_ticks": reservation_amount, "case_id": case_id, "created_at": _iso(now_value)})
        _write_reservations(directory, state["active_reservations"])
        result["reservation_id"] = reservation_id
        result["reserved_cost_ticks"] = reservation_amount
    _decision_event(directory, result, query_fp=fp, case_id=case_id, model=model, estimated_input_tokens=estimated_input_tokens)
    return result


def _response_dump(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        try:
            value = response.model_dump()
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    return response if isinstance(response, dict) else {}


def _settle_reservation(directory: Path, reservation_id: str | None) -> int | None:
    if not reservation_id:
        return None
    reservations = _read_reservations(directory)
    selected = next((item for item in reservations if item.get("reservation_id") == reservation_id), None)
    if selected is None:
        raise RuntimeError("Grok cost reservation is missing; accounting denied")
    return selected["amount_ticks"]


def _remove_settled_reservation(directory: Path, reservation_id: str) -> None:
    reservations = _read_reservations(directory)
    _write_reservations(directory, [item for item in reservations if item.get("reservation_id") != reservation_id])


def _existing_settlement(events: list[dict[str, Any]], reservation_id: str | None) -> dict[str, Any] | None:
    return next((event for event in reversed(events) if event.get("reservation_id") == reservation_id and event.get("event_type") == "SETTLEMENT"), None)


def record_xai_response(response: Any, *, model: str, query: str, case_id: str | None, latency_ms: float | None, reservation_id: str | None = None, task_type: str = "GROK_X_SEARCH") -> dict[str, Any]:
    dump = _response_dump(response)
    usage = dump.get("usage") if isinstance(dump.get("usage"), dict) else {}
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    provider_ticks = usage.get("cost_in_usd_ticks")
    ticks = provider_ticks if isinstance(provider_ticks, int) and not isinstance(provider_ticks, bool) and provider_ticks >= 0 else None
    with _ledger_lock() as directory:
        existing = _existing_settlement(_read_events(directory), reservation_id)
        if existing is not None:
            _remove_settled_reservation(directory, str(reservation_id))
            return existing
        reservation_ticks = _settle_reservation(directory, reservation_id)
        settled_ticks = ticks if ticks is not None else reservation_ticks
        if settled_ticks is None:
            raise RuntimeError("Grok response cost is unavailable without a reservation; accounting denied")
        row = _accounting_row(
            completed=True,
            model=model,
            query=query,
            case_id=case_id,
            latency_ms=latency_ms,
            task_type=task_type,
            cost_ticks=settled_ticks,
            cost_source="XAI_COST_IN_USD_TICKS" if ticks is not None else "RESERVATION_CONSERVATIVE_ESTIMATE",
            usage=usage,
        )
        row["event_type"] = "SETTLEMENT"
        row["reservation_id"] = reservation_id
        if ticks is not None and ticks > reservation_ticks:
            row["budget_integrity_breach"] = True
        if row.get("budget_integrity_breach"):
            _atomic_json_write(directory, INTEGRITY_NAME, {"blocked": True, "reason": "EXACT_COST_EXCEEDED_RESERVATION"})
        _append_jsonl(directory / LEDGER_NAME, row)
        _remove_settled_reservation(directory, str(reservation_id))
        _publish_governor_artifact(directory)
        return row


def _accounting_row(*, completed: bool, model: str, query: str, case_id: str | None, latency_ms: float | None, task_type: str, cost_ticks: int, cost_source: str, usage: dict[str, Any]) -> dict[str, Any]:
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    tool_calls = _int(usage.get("num_server_side_tools_used"))
    return {
        "timestamp": _iso(_utc_now()),
        "provider": "XAI",
        "model": model,
        "task_type": task_type,
        "case_id": case_id,
        "agent": "GROK_SOCIAL_INTELLIGENCE",
        "input_tokens": _int(usage.get("input_tokens")),
        "cached_input_tokens": _int(details.get("cached_tokens")),
        "output_tokens": _int(usage.get("output_tokens")),
        "web_search_calls": 0,
        "x_search_calls": tool_calls,
        "server_side_tool_calls": tool_calls,
        "cost_ticks": cost_ticks,
        "cost_source": cost_source,
        "cost_in_usd_ticks": cost_ticks if cost_source == "XAI_COST_IN_USD_TICKS" else None,
        "latency_ms": _float(latency_ms),
        "query_fingerprint": query_fingerprint(query),
        "request_completed": completed,
        "prompt_persisted": False,
        "api_key_persisted": False,
    }


def record_xai_failure(*, model: str, query: str, case_id: str | None, latency_ms: float | None, error_type: str, reservation_id: str | None = None, task_type: str = "GROK_X_SEARCH") -> dict[str, Any]:
    with _ledger_lock() as directory:
        existing = _existing_settlement(_read_events(directory), reservation_id)
        if existing is not None:
            _remove_settled_reservation(directory, str(reservation_id))
            return existing
        reservation_ticks = _settle_reservation(directory, reservation_id)
        if reservation_ticks is None:
            raise RuntimeError("Grok failed request has no reservation; accounting denied")
        existing = _existing_settlement(_read_events(directory), reservation_id)
        if existing is not None:
            _remove_settled_reservation(directory, str(reservation_id))
            return existing
        row = _accounting_row(
            completed=False, model=model, query=query, case_id=case_id, latency_ms=latency_ms, task_type=task_type,
            cost_ticks=reservation_ticks, cost_source="RESERVATION_CONSERVATIVE_ESTIMATE", usage={},
        )
        row["event_type"] = "SETTLEMENT"
        row["reservation_id"] = reservation_id
        row["error_type"] = sanitize_error(error_type) or "UNKNOWN"
        _append_jsonl(directory / LEDGER_NAME, row)
        _remove_settled_reservation(directory, str(reservation_id))
        _publish_governor_artifact(directory)
        return row


def register_hook() -> dict[str, Any]:
    with _ledger_lock() as cost_dir:
        return _register_hook(cost_dir)


def _register_hook(cost_dir: Path) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _iso(_utc_now()),
        "hooks": {
            "xai_grok_social_intelligence": {
                "connected": True,
                "binding": True,
                "pre_call_admission": True,
                "post_call_exact_cost": True,
                "prompt_persisted": False,
                "api_key_persisted": False,
            }
        },
        "trade_execution_permission": False,
        "capital_authority": False,
        "live_execution": False,
    }
    _atomic_json_write(cost_dir, HOOK_REGISTRY_NAME, payload)
    _publish_governor_artifact(cost_dir)
    return payload


def publish_governor_artifact() -> dict[str, Any]:
    with _ledger_lock() as cost_dir:
        return _publish_governor_artifact(cost_dir)


def _publish_governor_artifact(cost_dir: Path) -> dict[str, Any]:
    state = _current_state(cost_dir)
    week = list(state["week"])
    today = list(state["today"])
    priced = list(week)
    unpriced = len(week) - len(priced)
    coverage = round((len(priced) / len(week) * 100.0), 1) if week else 0.0
    daily = state["daily_exact_spend_ticks"]
    weekly = state["weekly_exact_spend_ticks"]
    if daily >= POLICY["daily_hard_limit_ticks"] or weekly >= POLICY["rolling_7d_hard_limit_ticks"]:
        budget_state = "HARD_LIMIT"
    elif daily >= POLICY["daily_soft_limit_ticks"] or weekly >= POLICY["rolling_7d_soft_limit_ticks"]:
        budget_state = "SOFT_LIMIT"
    else:
        budget_state = "WITHIN_BUDGET" if week else "INSTRUMENTATION_BOOTSTRAP"

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(_utc_now()),
        "status": "MODEL_COST_GOVERNOR_ENFORCEMENT_ACTIVE",
        "budget_state": budget_state,
        "enforcement_hooks_connected": True,
        "binding_xai_grok_hook": True,
        "exact_cost_policy": "XAI_COST_IN_USD_TICKS_ONLY_FOR_DOLLAR_TOTALS",
        "no_spend_estimate_invented": True,
        "policy": dict(POLICY),
        "today": {
            "requests": len(today),
            "priced_requests": sum(1 for row in today if _float(row.get("cost_usd")) is not None),
            "exact_spend_ticks": daily if today else None,
            "input_tokens": sum(_int(row.get("input_tokens")) for row in today),
            "cached_input_tokens": sum(_int(row.get("cached_input_tokens")) for row in today),
            "output_tokens": sum(_int(row.get("output_tokens")) for row in today),
            "x_search_calls": sum(_int(row.get("x_search_calls")) for row in today),
        },
        "rolling_7d": {
            "requests": len(week),
            "priced_requests": len(priced),
            "unpriced_requests": unpriced,
            "exact_cost_coverage_pct": coverage,
            "exact_spend_ticks": weekly if week else None,
            "input_tokens": sum(_int(row.get("input_tokens")) for row in week),
            "cached_input_tokens": sum(_int(row.get("cached_input_tokens")) for row in week),
            "output_tokens": sum(_int(row.get("output_tokens")) for row in week),
            "x_search_calls": sum(_int(row.get("x_search_calls")) for row in week),
        },
        "measurement_gaps": (["NO_POST_HOOK_XAI_REQUEST_RECORDED_YET"] if not week else []) + (["SOME_FAILED_REQUESTS_HAVE_NO_PROVIDER_REPORTED_EXACT_COST"] if unpriced else []),
        "safety": {
            "scope": "XAI_GROK_RESEARCH_COST_ONLY",
            "auto_trade_authority": False,
            "paper_order_permission": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "no_model_weight_change": True,
            "no_portfolio_change": True,
        },
    }
    _atomic_json_write(cost_dir, ARTIFACT_NAME, artifact)
    return artifact


def main() -> int:
    hook = register_hook()
    artifact = publish_governor_artifact()
    print(json.dumps({
        "status": artifact["status"],
        "budget_state": artifact["budget_state"],
        "enforcement_hooks_connected": artifact["enforcement_hooks_connected"],
        "rolling_7d_exact_spend_usd": (artifact.get("rolling_7d") or {}).get("exact_spend_usd"),
        "hook": hook["hooks"]["xai_grok_social_intelligence"],
        "trade_execution_permission": False,
        "capital_authority": False,
        "live_execution": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
