from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .projection import build_living_wall_projection

router = APIRouter(prefix="/expansion-wing", tags=["Expansion Wing"])


def _snapshot_source() -> dict[str, Any]:
    configured = os.getenv("IIOS_EXPANSION_WING_SANITIZED_SNAPSHOT", "").strip()
    if not configured:
        return {}
    path = Path(configured).expanduser().resolve()
    if path.suffix.lower() != ".json" or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


@router.get("/status")
def expansion_wing_status() -> dict[str, Any]:
    """Expose sanitized state only; absence is truthful UNAVAILABLE state."""
    projection = build_living_wall_projection(_snapshot_source())
    projection["rooms"] = [
        "Interview Studio", "Investor Archive", "Philosophy Arena", "Judgment Foundry",
        "Pattern Laboratory", "Strictness Observatory", "Cross-Asset Observatory", "Regime Chamber",
        "Tactical Book", "Strategic Book", "Capital Allocation Room", "Failure Museum",
        "Strategy Incubator", "Learning Theater",
    ]
    return projection
