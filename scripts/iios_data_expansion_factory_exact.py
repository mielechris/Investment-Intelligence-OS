#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import iios_chief_intelligence_office as chief
import iios_data_expansion_factory as base
import iios_experiment_ab_laboratory as lab


def build_from_state(state_dir: Path, telemetry_dir: Path) -> dict[str, Any]:
    office = chief.build_from_state(state_dir, telemetry_dir)
    experiment_lab = lab.build_from_state(state_dir, telemetry_dir)
    return base.build_data_expansion_factory(
        office=office,
        lab=experiment_lab,
        scorecard=base._read_json(state_dir / "latest_market_validation.json"),
        telemetry=base._read_json(telemetry_dir / "latest.json"),
    )
