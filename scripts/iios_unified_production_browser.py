#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import iios_agent_performance_league as league
import iios_chief_intelligence_office as chief
import iios_data_expansion_factory as data_factory
import iios_experiment_ab_laboratory as lab
import iios_market_regime_intelligence as regime
import iios_paper_performance_qualification as qualification
import iios_portfolio_intelligence as portfolio

SCHEMA_VERSION = "batch10a-unified-production-browser-v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file(): return {}
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_unified(*, state_dir: Path, telemetry_dir: Path, generated_at: datetime | None = None) -> dict[str, Any]:
    scorecard = _read_json(state_dir / "latest_market_validation.json")
    learning = _read_json(state_dir / "latest_outcome_learning.json")
    shadow = _read_json(state_dir / "shadow_strategy" / "latest_shadow_counterfactual.json")
    telemetry = _read_json(telemetry_dir / "latest.json")
    office = chief.build_from_state(state_dir, telemetry_dir)
    experiments = lab.build_from_state(state_dir, telemetry_dir)
    expansion = data_factory.build_from_state(state_dir, telemetry_dir)
    league_payload = league.build_from_state(state_dir, telemetry_dir)
    regime_payload = regime.build_regime(scorecard=scorecard, learning=learning, league=league_payload, telemetry=telemetry)
    paper = qualification.build_qualification(telemetry=telemetry, learning=learning, scorecard=scorecard)
    portfolio_payload = portfolio.build_portfolio(telemetry=telemetry)
    modules = [
        {"code":"9G","name":"Factory Telemetry","status":"AVAILABLE" if telemetry else "WAITING"},
        {"code":"9H","name":"Independent Validation","status":scorecard.get("status") or ("AVAILABLE" if scorecard else "WAITING")},
        {"code":"9I","name":"Shadow Strategy","status":shadow.get("status") or "WAITING"},
        {"code":"9J","name":"Outcome Learning","status":learning.get("status") or "WAITING"},
        {"code":"9P","name":"Chief Intelligence Office","status":office.get("status")},
        {"code":"9Q","name":"Experiment Lab","status":experiments.get("status")},
        {"code":"9R","name":"Data Expansion","status":expansion.get("status")},
        {"code":"9S","name":"Agent Performance League","status":league_payload.get("status")},
        {"code":"9T","name":"Market Regime Intelligence","status":regime_payload.get("status")},
        {"code":"10B","name":"Paper Performance Qualification","status":paper.get("status")},
        {"code":"10C","name":"Portfolio Intelligence","status":portfolio_payload.get("status")},
    ]
    blockers = [row for row in paper.get("gates") or [] if isinstance(row, dict) and row.get("state") != "PASS"]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "status": "UNIFIED_OPERATING_BROWSER_READY",
        "operating_mode": "GOVERNED_PAPER_RESEARCH_ONLY",
        "live_capital_mode": False,
        "modules": modules,
        "capital_readiness_blockers": blockers,
        "paper_qualification": paper,
        "portfolio_intelligence": portfolio_payload,
        "regime": regime_payload.get("current_regime"),
        "summary": {
            "module_count": len(modules),
            "paper_qualification_status": paper.get("status"),
            "paper_nav": portfolio_payload.get("nav"),
            "paper_positions": portfolio_payload.get("position_count"),
            "capital_readiness_blocker_count": len(blockers),
        },
        "safety": {
            "browser_is_command_surface": False,
            "backend_write_permission": False,
            "auto_advance_capital": False,
            "broker_connection_authority": False,
            "capital_authority": False,
            "trade_execution_permission": False,
            "live_execution": False,
            "human_approval_required": True,
        },
    }
