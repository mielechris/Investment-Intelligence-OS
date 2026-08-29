#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from model_agent_health_watchdog import publish_health_artifact  # noqa: E402


def main() -> int:
    snapshot = publish_health_artifact(db_path=os.getenv("IIOS_DB_PATH"))
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0 if snapshot.get("overall_state") in {"HEALTHY", "IDLE_HEALTHY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
