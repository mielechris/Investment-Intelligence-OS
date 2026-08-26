from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_USER_AGENT = os.getenv(
    "IIOS_USER_AGENT",
    "Investment-Intelligence-OS/0.16.0 research-client",
)

SCENARIOS = {
    "CUT_100",
    "CUT_75",
    "CUT_50",
    "CUT_25",
    "HOLD",
    "HIKE_25",
    "HIKE_50",
    "HIKE_75",
    "HIKE_100",
}



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configured_mode() -> str:
    raw = str(os.getenv("IIOS_CME_FEDWATCH_MODE") or "EOD").strip().upper()
    return raw if raw in {"EOD", "REALTIME"} else "EOD"


def _approved_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "cmegroup.com" or host.endswith(".cmegroup.com")


def configuration_status() -> dict[str, Any]:
    url = str(os.getenv("IIOS_CME_FEDWATCH_URL") or "").strip()
    key_present = bool(str(os.getenv("IIOS_CME_FEDWATCH_API_KEY") or "").strip())
    return {
        "configured": bool(url),
        "mode": configured_mode(),
        "url_host": (urlparse(url).hostname or None) if url else None,
        "approved_cme_host": _approved_host(url) if url else False,
        "credential_present": key_present,
        "credential_exposed": False,
        "trade_execution_permission": False,
        "live_execution": False,
    }


def _auth_headers() -> dict[str, str]:
    key = str(os.getenv("IIOS_CME_FEDWATCH_API_KEY") or "").strip()
    if not key:
        return {}

    header_name = str(
        os.getenv("IIOS_CME_FEDWATCH_HEADER_NAME") or "X-API-Key"
    ).strip() or "X-API-Key"
    scheme = str(os.getenv("IIOS_CME_FEDWATCH_AUTH_SCHEME") or "RAW").strip().upper()

    if scheme == "BEARER":
        value = f"Bearer {key}"
    else:
        value = key
    return {header_name: value}


def _fetch_json(url: str) -> Any:
    if not _approved_host(url):
        raise ValueError("FedWatch URL must use an official cmegroup.com host")

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
        **_auth_headers(),
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _number(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("raw", "value", "probability", "prob", "percentage", "pct"):
            if key in value:
                return _number(value.get(key))
        return None
    try:
        number = float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return number


def _canonical_scenario(label: Any) -> str | None:
    raw = str(label or "").strip().upper().replace("-", "_").replace(" ", "_")
    raw = re.sub(r"_+", "_", raw)
    aliases = {
        "UNCHANGED": "HOLD",
        "NO_CHANGE": "HOLD",
        "NOCHANGE": "HOLD",
        "HOLD": "HOLD",
        "CUT25": "CUT_25",
        "CUT_25BP": "CUT_25",
        "CUT_25_BPS": "CUT_25",
        "CUT_25": "CUT_25",
        "CUT50": "CUT_50",
        "CUT_50BP": "CUT_50",
        "CUT_50_BPS": "CUT_50",
        "CUT_50": "CUT_50",
        "CUT75": "CUT_75",
        "CUT_75BP": "CUT_75",
        "CUT_75_BPS": "CUT_75",
        "CUT_75": "CUT_75",
        "CUT100": "CUT_100",
        "CUT_100BP": "CUT_100",
        "CUT_100_BPS": "CUT_100",
        "CUT_100": "CUT_100",
        "HIKE25": "HIKE_25",
        "HIKE_25BP": "HIKE_25",
        "HIKE_25_BPS": "HIKE_25",
        "HIKE_25": "HIKE_25",
        "HIKE50": "HIKE_50",
        "HIKE_50BP": "HIKE_50",
        "HIKE_50_BPS": "HIKE_50",
        "HIKE_50": "HIKE_50",
        "HIKE75": "HIKE_75",
        "HIKE_75BP": "HIKE_75",
        "HIKE_75_BPS": "HIKE_75",
        "HIKE_75": "HIKE_75",
        "HIKE100": "HIKE_100",
        "HIKE_100BP": "HIKE_100",
        "HIKE_100_BPS": "HIKE_100",
        "HIKE_100": "HIKE_100",
    }
    if raw in aliases:
        return aliases[raw]

    match = re.search(r"(CUT|HIKE).*?(25|50|75|100)", raw)
    if match:
        candidate = f"{match.group(1)}_{match.group(2)}"
        return candidate if candidate in SCENARIOS else None
    if "HOLD" in raw or "UNCHANGED" in raw or "NO_CHANGE" in raw:
        return "HOLD"
    return None


def _distribution_from_mapping(mapping: dict[str, Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for key, value in mapping.items():
        scenario = _canonical_scenario(key)
        number = _number(value)
        if scenario and number is not None and number >= 0:
            output[scenario] = output.get(scenario, 0.0) + number
    return output


def _row_label(row: dict[str, Any]) -> Any:
    for key in (
        "scenario",
        "outcome",
        "change",
        "action",
        "rateChange",
        "rate_change",
        "label",
        "name",
    ):
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _row_probability(row: dict[str, Any]) -> float | None:
    for key in (
        "probability",
        "prob",
        "percentage",
        "percent",
        "pct",
        "value",
    ):
        if key in row:
            number = _number(row.get(key))
            if number is not None:
                return number
    return None


def _distribution_from_rows(rows: list[Any]) -> dict[str, float]:
    output: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        scenario = _canonical_scenario(_row_label(row))
        probability = _row_probability(row)
        if scenario and probability is not None and probability >= 0:
            output[scenario] = output.get(scenario, 0.0) + probability
    return output


def _candidate_distributions(payload: Any) -> list[dict[str, float]]:
    candidates: list[dict[str, float]] = []

    if isinstance(payload, dict):
        for key in (
            "probabilities",
            "probabilityDistribution",
            "probability_distribution",
            "distribution",
            "outcomes",
        ):
            value = payload.get(key)
            if isinstance(value, dict):
                candidates.append(_distribution_from_mapping(value))
            elif isinstance(value, list):
                candidates.append(_distribution_from_rows(value))

        for key in ("data", "results", "meetings", "events"):
            value = payload.get(key)
            if isinstance(value, list):
                row_distribution = _distribution_from_rows(value)
                if row_distribution:
                    candidates.append(row_distribution)
                for row in value:
                    if isinstance(row, dict):
                        candidates.extend(_candidate_distributions(row))
            elif isinstance(value, dict):
                candidates.extend(_candidate_distributions(value))

        direct = _distribution_from_mapping(payload)
        if direct:
            candidates.append(direct)

    elif isinstance(payload, list):
        candidates.append(_distribution_from_rows(payload))
        for row in payload:
            candidates.extend(_candidate_distributions(row))

    return [x for x in candidates if x]


def normalize_fedwatch_payload(payload: Any) -> dict[str, Any]:
    candidates = _candidate_distributions(payload)
    if not candidates:
        raise ValueError(
            "FedWatch payload did not expose a scenario-labelled probability distribution. "
            "No probabilities were inferred from target-rate ranges."
        )

    # Prefer the distribution with the greatest mapped scenario breadth; then the
    # largest probability mass. This avoids silently selecting a partial nested row.
    distribution = max(
        candidates,
        key=lambda row: (len(row), sum(row.values())),
    )

    total = sum(distribution.values())
    if total <= 0:
        raise ValueError("FedWatch probability total must be positive")
    if total > 1.5:
        normalized = {key: value / 100.0 for key, value in distribution.items()}
    else:
        normalized = dict(distribution)
    total = sum(normalized.values())
    normalized = {key: value / total for key, value in normalized.items()}

    return {
        "probabilities": {key: round(value, 8) for key, value in normalized.items()},
        "source_name": f"CME FedWatch API ({configured_mode()})",
        "source_verified": True,
        "source_mode": f"CME_FEDWATCH_{configured_mode()}",
        "probabilities_invented": False,
    }


def fetch_cme_fedwatch() -> dict[str, Any]:
    url = str(os.getenv("IIOS_CME_FEDWATCH_URL") or "").strip()
    if not url:
        return {
            "status": "SOURCE_NOT_CONFIGURED",
            "configuration": configuration_status(),
            "probabilities_invented": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    try:
        payload = _fetch_json(url)
        normalized = normalize_fedwatch_payload(payload)
    except Exception as exc:
        return {
            "status": "SOURCE_ERROR",
            "configuration": configuration_status(),
            "error": f"{type(exc).__name__}: {exc}",
            "probabilities_invented": False,
            "trade_execution_permission": False,
            "live_execution": False,
        }

    return {
        "status": "CAPTURED",
        **normalized,
        "configuration": configuration_status(),
        "captured_at": utc_now(),
        "trade_execution_permission": False,
        "live_execution": False,
    }
