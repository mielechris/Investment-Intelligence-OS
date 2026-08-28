#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "BACK END" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from market_validation_scorecard import (  # noqa: E402
    DEFAULT_MAX_LAG_MINUTES,
    DEFAULT_MAX_LEAD_MINUTES,
    build_market_validation_scorecard,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the read-only IIOS Batch 9G end-of-session market "
            "validation scorecard from a supplied opportunity-set JSON file."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the supplied market opportunity-set JSON file.",
    )
    parser.add_argument(
        "--db",
        help="Optional IIOS ledger path; defaults to IIOS_DB_PATH.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--max-lead-minutes",
        type=int,
        default=DEFAULT_MAX_LEAD_MINUTES,
        help=(
            "How early a same-ticker IIOS detection can be and still "
            "match the supplied market opportunity."
        ),
    )
    parser.add_argument(
        "--max-lag-minutes",
        type=int,
        default=DEFAULT_MAX_LAG_MINUTES,
        help=(
            "Maximum lag after the supplied market event for a same-ticker "
            "IIOS detection to count as detected."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    scorecard = build_market_validation_scorecard(
        payload,
        args.db,
        max_lead_minutes=args.max_lead_minutes,
        max_lag_minutes=args.max_lag_minutes,
    )
    text = json.dumps(
        scorecard,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(output)
        print(
            json.dumps(
                {
                    "status": "BATCH9G_SCORECARD_WRITTEN",
                    "output": str(output),
                    "opportunity_count": scorecard["metrics"][
                        "opportunity_count"
                    ],
                    "detected_count": scorecard["metrics"][
                        "detected_count"
                    ],
                    "missed_count": scorecard["metrics"]["missed_count"],
                    "paper_fill_count": scorecard["metrics"][
                        "paper_fill_count"
                    ],
                    "live_execution": False,
                },
                sort_keys=True,
            )
        )
    else:
        print(text, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
