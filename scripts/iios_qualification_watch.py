#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "batch10g-qualification-watch-v1"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "market-validation"
DEFAULT_TELEMETRY_DIR = Path.home() / "Library" / "Application Support" / "IIOS" / "telemetry"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_required(text: str) -> float | None:
    digits = "".join(ch for ch in str(text or "") if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def build_watch(*, qualification: dict[str, Any], readiness: dict[str, Any], generated_at: datetime | None = None) -> dict[str, Any]:
    gates = [row for row in qualification.get("gates") or [] if isinstance(row, dict)]
    progress_rows: list[dict[str, Any]] = []
    sample_gate_names = {"COMPLETE_VALIDATION_SESSIONS", "GOVERNED_PAPER_TRANSACTIONS", "MATURE_5D_OUTCOMES"}
    for row in gates:
        name = str(row.get("gate") or "UNKNOWN")
        observed = _num(row.get("observed"))
        required = _parse_required(str(row.get("required") or ""))
        if name in sample_gate_names and required and required > 0:
            ratio = min(1.0, observed / required)
            remaining = max(0.0, required - observed)
        else:
            ratio = 1.0 if row.get("state") == "PASS" else 0.0
            remaining = None
        progress_rows.append({
            "gate": name,
            "state": row.get("state"),
            "observed": row.get("observed"),
            "required": row.get("required"),
            "progress_pct": round(ratio * 100.0, 1),
            "remaining": remaining,
        })

    sample_rows = [row for row in progress_rows if row["gate"] in sample_gate_names]
    qualification_progress = round(sum(row["progress_pct"] for row in sample_rows) / len(sample_rows), 1) if sample_rows else 0.0
    unresolved = [row for row in readiness.get("gates") or [] if isinstance(row, dict) and str(row.get("state") or "").upper() not in {"PASS", "COMPLETE"}]
    sample_complete = qualification.get("sample_ready") is True
    phase = "HUMAN_READINESS_REVIEW_ELIGIBLE" if str(qualification.get("status")) == "PAPER_QUALIFIED_FOR_HUMAN_READINESS_REVIEW" else "GOVERNED_PAPER_EVIDENCE_COLLECTION"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "QUALIFICATION_WATCH_ACTIVE",
        "phase": phase,
        "qualification_status": qualification.get("status"),
        "capital_readiness_status": readiness.get("status"),
        "qualification_progress_pct": qualification_progress,
        "sample_ready": sample_complete,
        "progress": progress_rows,
        "unresolved_readiness_gate_count": len(unresolved),
        "unresolved_readiness_gates": [str(row.get("gate") or row.get("name") or "UNKNOWN") for row in unresolved],
        "next_action": (
            "HUMAN_READINESS_REVIEW" if sample_complete else "CONTINUE_GOVERNED_PAPER_COLLECTION"
        ),
        "completion_definition": {
            "engineering": "COMPLETE",
            "paper_qualification": "COMPLETE only when the persisted 10B rubric passes",
            "capital_readiness": "Requires separate human/legal/broker/custodian approvals after paper qualification",
        },
        "safety": {
            "watch_only": True,
            "paper_only": True,
            "auto_generate_trades": False,
            "auto_change_thresholds": False,
            "auto_change_agent_weights": False,
            "auto_connect_broker": False,
            "auto_fund_account": False,
            "auto_enable_live": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }


def build_from_browser(browser_dir: Path) -> dict[str, Any]:
    return build_watch(
        qualification=_read_json(browser_dir / "paper_performance_qualification.json"),
        readiness=_read_json(browser_dir / "governed_capital_readiness.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the read-only IIOS paper qualification watch artifact.")
    parser.add_argument("--browser-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    payload = build_from_browser(Path(args.browser_dir).expanduser())
    output = Path(args.output).expanduser() if args.output else Path(args.browser_dir).expanduser() / "qualification_watch.json"
    _atomic_write(output, payload)
    print(json.dumps({"status": payload["status"], "phase": payload["phase"], "qualification_progress_pct": payload["qualification_progress_pct"], "live_execution": False, "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
