#!/usr/bin/env python3
"""Publish one fail-closed Living Wall snapshot to the approved Vercel Preview."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator
from urllib.parse import urlparse


REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO / "config" / "preview_living_wall_publisher.json"
PUBLISHER_PATH = REPO / "scripts" / "publish_remote_telemetry.py"
EXPECTED_SCHEMA = "iios_preview_living_wall_publisher.v1"
EXPECTED_LABEL = "com.iios.living-wall-preview-publisher"
EXPECTED_BRANCH = "feature/iios-living-wall-gallery"
EXPECTED_PREVIEW_HOST = (
    "investment-intelligence-os-git-feature-iios-l-104899-chris-2274.vercel.app"
)
EXPECTED_LOCAL_SOURCE = "http://127.0.0.1:5176/living/overview"
EXPECTED_INGEST_PATH = "/telemetry/ingest"
EXPECTED_TRUTH_PATH = "/living-wall/truth"
EXPECTED_INGEST_KEYCHAIN = {
    "service": "com.iios.living-wall-preview.ingest",
    "account": "feature/iios-living-wall-gallery",
}
EXPECTED_BYPASS_KEYCHAIN = {
    "service": "com.iios.living-wall-preview.vercel-bypass",
    "account": "investment-intelligence-os",
}
EXPECTED_STATE_DIRECTORY = "~/Library/Application Support/IIOS/LivingWallPublisher"
EXPECTED_LOG_PATH = "~/Library/Logs/IIOS/living-wall-preview-publisher.log"
MAX_RESPONSE_BYTES = 512 * 1024
SAFE_EVENT_CODES = {
    "BACKOFF_ACTIVE",
    "CYCLE_FAILED",
    "CYCLE_OK",
    "HEALTH_FAILED",
    "HEALTH_OK",
    "LOCK_HELD",
}
SAFE_FAILURE_CODES = {
    "DESTINATION_HOST_REJECTED", "DESTINATION_NOT_BRANCH_ALIAS",
    "DESTINATION_PATH_REJECTED", "GET_CONTRACT_REJECTED", "INGEST_REJECTED",
    "KEYCHAIN_READ_FAILED", "LOCAL_TRUTH_REJECTED", "METHOD_REJECTED",
    "POLICY_BOUNDARY_INVALID", "POLICY_KEYCHAIN_INVALID", "POLICY_KEYS_INVALID",
    "POLICY_LOAD_FAILED", "POST_CONTRACT_REJECTED", "PUBLISHER_LOAD_FAILED",
    "REMOTE_REQUEST_FAILED", "REMOTE_RESPONSE_INVALID", "REMOTE_TIMEOUT",
    "REMOTE_TRUTH_UNSAFE", "SECRET_FORMAT_REJECTED", "UNEXPECTED_FAILURE",
}


class PublisherFailure(RuntimeError):
    """A bounded failure whose code is safe to persist and log."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _publisher_module() -> Any:
    spec = importlib.util.spec_from_file_location("iios_remote_publisher", PUBLISHER_PATH)
    if spec is None or spec.loader is None:
        raise PublisherFailure("PUBLISHER_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublisherFailure("POLICY_LOAD_FAILED") from error
    required = {
        "schema_version", "label", "branch", "preview_host", "ingest_path",
        "truth_path", "local_source", "source_max_age_seconds",
        "future_skew_seconds", "connect_timeout_seconds", "request_timeout_seconds",
        "interval_seconds", "backoff_seconds", "ingest_keychain", "bypass_keychain",
        "state_directory", "log_path",
    }
    if not isinstance(policy, dict) or set(policy) != required:
        raise PublisherFailure("POLICY_KEYS_INVALID")
    if (
        policy["schema_version"] != EXPECTED_SCHEMA
        or policy["label"] != EXPECTED_LABEL
        or policy["branch"] != EXPECTED_BRANCH
        or policy["preview_host"] != EXPECTED_PREVIEW_HOST
        or policy["local_source"] != EXPECTED_LOCAL_SOURCE
        or policy["ingest_path"] != EXPECTED_INGEST_PATH
        or policy["truth_path"] != EXPECTED_TRUTH_PATH
        or policy["source_max_age_seconds"] != 30
        or policy["future_skew_seconds"] != 5
        or policy["connect_timeout_seconds"] != 5
        or policy["request_timeout_seconds"] != 15
        or policy["interval_seconds"] != 30
        or policy["backoff_seconds"] != [30, 60, 120, 300]
        or policy["ingest_keychain"] != EXPECTED_INGEST_KEYCHAIN
        or policy["bypass_keychain"] != EXPECTED_BYPASS_KEYCHAIN
        or policy["state_directory"] != EXPECTED_STATE_DIRECTORY
        or policy["log_path"] != EXPECTED_LOG_PATH
    ):
        raise PublisherFailure("POLICY_BOUNDARY_INVALID")
    for key in ("ingest_keychain", "bypass_keychain"):
        item = policy[key]
        if not isinstance(item, dict) or set(item) != {"service", "account"}:
            raise PublisherFailure("POLICY_KEYCHAIN_INVALID")
        if not all(isinstance(item[value], str) and item[value] for value in item):
            raise PublisherFailure("POLICY_KEYCHAIN_INVALID")
    validate_destination(policy, policy["ingest_path"])
    validate_destination(policy, policy["truth_path"])
    return policy


def validate_destination(policy: dict[str, Any], path: str) -> str:
    if path not in {EXPECTED_INGEST_PATH, EXPECTED_TRUTH_PATH}:
        raise PublisherFailure("DESTINATION_PATH_REJECTED")
    url = f"https://{policy.get('preview_host', '')}{path}"
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != EXPECTED_PREVIEW_HOST
        or parsed.port is not None
        or parsed.path != path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise PublisherFailure("DESTINATION_HOST_REJECTED")
    if "-git-feature-iios-l-104899-" not in parsed.hostname:
        raise PublisherFailure("DESTINATION_NOT_BRANCH_ALIAS")
    return url


def expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    ensure_private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_state(policy: dict[str, Any]) -> dict[str, Any]:
    path = expanded_path(policy["state_directory"]) / "status.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"consecutive_failures": 0, "next_attempt_at": None}
    if not isinstance(value, dict):
        return {"consecutive_failures": 0, "next_attempt_at": None}
    return value


def write_status(policy: dict[str, Any], **values: Any) -> None:
    allowed = {
        "event", "failure_code", "observed_at", "last_attempt_at", "last_success_at",
        "next_attempt_at", "consecutive_failures", "http_status", "availability",
        "freshness", "age_seconds", "live_execution", "telemetry_read_only",
    }
    safe = {key: value for key, value in values.items() if key in allowed}
    if safe.get("failure_code") not in SAFE_FAILURE_CODES:
        safe.pop("failure_code", None)
    _atomic_json(expanded_path(policy["state_directory"]) / "status.json", safe)


def append_log(policy: dict[str, Any], event: str, **fields: Any) -> None:
    safe_event = event if event in SAFE_EVENT_CODES else "CYCLE_FAILED"
    allowed = {
        "failure_code", "http_status", "availability", "freshness", "age_seconds",
        "consecutive_failures", "next_attempt_at",
    }
    record = {"at": utc_now().isoformat(), "event": safe_event}
    record.update({key: value for key, value in fields.items() if key in allowed})
    if record.get("failure_code") not in SAFE_FAILURE_CODES:
        record.pop("failure_code", None)
    path = expanded_path(policy["log_path"])
    ensure_private_directory(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, (json.dumps(record, sort_keys=True) + "\n").encode())
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


@contextmanager
def publisher_lock(policy: dict[str, Any]) -> Iterator[bool]:
    directory = expanded_path(policy["state_directory"])
    ensure_private_directory(directory)
    path = directory / "publisher.lock"
    handle = path.open("a+")
    os.chmod(path, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def keychain_secret(item: dict[str, str]) -> str:
    command = [
        "/usr/bin/security", "find-generic-password", "-s", item["service"],
        "-a", item["account"], "-w",
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            check=False,
            env={"PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublisherFailure("KEYCHAIN_READ_FAILED") from error
    secret = result.stdout.rstrip("\r\n")
    if result.returncode != 0 or not secret or "\r" in secret or "\n" in secret:
        raise PublisherFailure("KEYCHAIN_READ_FAILED")
    return secret


def _curl_config(headers: dict[str, str]) -> bytes:
    lines: list[str] = []
    for name, value in headers.items():
        if any(char in value for char in "\r\n"):
            raise PublisherFailure("SECRET_FORMAT_REJECTED")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'header = "{name}: {escaped}"')
    return ("\n".join(lines) + "\n").encode()


def curl_json(
    policy: dict[str, Any],
    *,
    method: str,
    path: str,
    bypass_secret: str,
    ingest_token: str | None = None,
    payload: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    if method not in {"GET", "POST"}:
        raise PublisherFailure("METHOD_REJECTED")
    if method == "POST" and (path != EXPECTED_INGEST_PATH or payload is None or not ingest_token):
        raise PublisherFailure("POST_CONTRACT_REJECTED")
    if method == "GET" and (path != EXPECTED_TRUTH_PATH or payload is not None or ingest_token):
        raise PublisherFailure("GET_CONTRACT_REJECTED")
    url = validate_destination(policy, path)
    headers = {
        "Accept": "application/json",
        "x-vercel-protection-bypass": bypass_secret,
    }
    if method == "POST":
        headers["Content-Type"] = "application/json"
        headers["x-iios-telemetry-token"] = f"Bearer {ingest_token}"

    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, _curl_config(headers))
    finally:
        os.close(write_fd)
    command = [
        "/usr/bin/curl", "--disable", "--config", f"/dev/fd/{read_fd}", "--silent", "--show-error",
        "--no-buffer", "--request", method, "--connect-timeout",
        str(policy["connect_timeout_seconds"]), "--max-time",
        str(policy["request_timeout_seconds"]), "--max-redirs", "0", "--output", "-",
        "--max-filesize", str(MAX_RESPONSE_BYTES),
        "--write-out", "\n__IIOS_HTTP_STATUS__:%{http_code}",
    ]
    if method == "POST":
        command.extend(["--data-binary", "@-"])
    command.append(url)
    try:
        result = subprocess.run(
            command,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=policy["request_timeout_seconds"] + 1,
            check=False,
            pass_fds=(read_fd,),
            env={"PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublisherFailure("REMOTE_TIMEOUT") from error
    finally:
        os.close(read_fd)
    if result.returncode != 0 or len(result.stdout) > MAX_RESPONSE_BYTES + 64:
        raise PublisherFailure("REMOTE_REQUEST_FAILED")
    marker = b"\n__IIOS_HTTP_STATUS__:"
    if marker not in result.stdout:
        raise PublisherFailure("REMOTE_RESPONSE_INVALID")
    body, raw_status = result.stdout.rsplit(marker, 1)
    try:
        status = int(raw_status.strip())
        value = json.loads(body)
    except (ValueError, json.JSONDecodeError) as error:
        raise PublisherFailure("REMOTE_RESPONSE_INVALID") from error
    if not isinstance(value, dict):
        raise PublisherFailure("REMOTE_RESPONSE_INVALID")
    return status, value


def validate_remote_truth(status: int, truth: dict[str, Any]) -> dict[str, Any]:
    safety = truth.get("safety") if isinstance(truth.get("safety"), dict) else {}
    freshness = truth.get("freshness") if isinstance(truth.get("freshness"), dict) else {}
    if (
        status != 200
        or truth.get("schema_version") != "living_wall_truth.v1"
        or truth.get("availability") != "AVAILABLE"
        or freshness.get("state") != "CURRENT"
        or not isinstance(freshness.get("age_seconds"), int)
        or freshness["age_seconds"] > 60
        or safety.get("live_execution") is not False
        or safety.get("telemetry_read_only") is not True
        or safety.get("direct_ledger_access") is not False
        or safety.get("backend_write_permission") is not False
        or safety.get("trade_execution_permission") is not False
    ):
        raise PublisherFailure("REMOTE_TRUTH_UNSAFE")
    return {
        "http_status": status,
        "availability": truth["availability"],
        "freshness": freshness["state"],
        "age_seconds": freshness["age_seconds"],
        "live_execution": False,
        "telemetry_read_only": True,
    }


def publish_cycle(policy: dict[str, Any]) -> dict[str, Any]:
    module = _publisher_module()
    try:
        payload = module._read_snapshot(policy["local_source"])
    except Exception as error:
        raise PublisherFailure("LOCAL_TRUTH_REJECTED") from error
    ingest_token = keychain_secret(policy["ingest_keychain"])
    bypass_secret = keychain_secret(policy["bypass_keychain"])
    status, accepted = curl_json(
        policy, method="POST", path=policy["ingest_path"], bypass_secret=bypass_secret,
        ingest_token=ingest_token, payload=payload,
    )
    if status != 202 or accepted.get("accepted") is not True:
        raise PublisherFailure("INGEST_REJECTED")
    truth_status, truth = curl_json(
        policy, method="GET", path=policy["truth_path"], bypass_secret=bypass_secret,
    )
    return validate_remote_truth(truth_status, truth)


def health_check(policy: dict[str, Any]) -> dict[str, Any]:
    bypass_secret = keychain_secret(policy["bypass_keychain"])
    status, truth = curl_json(
        policy, method="GET", path=policy["truth_path"], bypass_secret=bypass_secret,
    )
    return validate_remote_truth(status, truth)


def _parse_timestamp(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def run_once(policy: dict[str, Any], now: datetime | None = None) -> int:
    observed = now or utc_now()
    with publisher_lock(policy) as acquired:
        if not acquired:
            append_log(policy, "LOCK_HELD")
            return 0
        previous = read_state(policy)
        next_at = _parse_timestamp(previous.get("next_attempt_at"))
        if next_at is not None and observed.timestamp() < next_at:
            append_log(policy, "BACKOFF_ACTIVE", next_attempt_at=previous.get("next_attempt_at"))
            return 0
        try:
            health = publish_cycle(policy)
        except PublisherFailure as error:
            failures = max(0, int(previous.get("consecutive_failures") or 0)) + 1
            delays = policy["backoff_seconds"]
            delay = delays[min(failures - 1, len(delays) - 1)]
            next_attempt = datetime.fromtimestamp(observed.timestamp() + delay, timezone.utc).isoformat()
            record = {
                "event": "CYCLE_FAILED", "failure_code": error.code,
                "observed_at": observed.isoformat(), "last_attempt_at": observed.isoformat(),
                "last_success_at": previous.get("last_success_at"),
                "next_attempt_at": next_attempt, "consecutive_failures": failures,
            }
            write_status(policy, **record)
            append_log(policy, "CYCLE_FAILED", failure_code=error.code,
                       consecutive_failures=failures, next_attempt_at=next_attempt)
            return 1
        record = {
            "event": "CYCLE_OK", "observed_at": observed.isoformat(),
            "last_attempt_at": observed.isoformat(), "last_success_at": observed.isoformat(),
            "next_attempt_at": None, "consecutive_failures": 0, **health,
        }
        write_status(policy, **record)
        append_log(policy, "CYCLE_OK", **health)
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="IIOS Preview Living Wall publisher")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    try:
        policy = load_policy()
        if args.health:
            result = health_check(policy)
            print(json.dumps({"status": "CURRENT", **result}, sort_keys=True))
            return 0
        return run_once(policy)
    except PublisherFailure as error:
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": error.code}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({"status": "FAILED_CLOSED", "failure_code": "UNEXPECTED_FAILURE"}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
