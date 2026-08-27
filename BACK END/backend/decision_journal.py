"""Append-only provenance journal for IIOS decisions.

The journal records observations and decisions, including NO_TRADE and VETO,
without granting order authority. Counterfactual records are explicitly shadow
only and cannot affect portfolio state.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


ALLOWED_EVENT_TYPES = frozenset({
    "DISCOVERED",
    "SCORED",
    "QUEUED",
    "PROMOTED",
    "DEEPENED",
    "MODEL_RESEARCH",
    "COMMITTEE_DECISION",
    "RISK_DECISION",
    "NO_TRADE",
    "REJECTED",
    "VETO",
    "PAPER_ORDER",
    "PAPER_FILL",
    "PAPER_CANCEL",
    "AFTER_ACTION",
    "COUNTERFACTUAL",
})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DecisionEvent:
    case_id: str
    ticker: str
    event_type: str
    decision: Optional[str] = None
    reason: Optional[str] = None
    score: Optional[float] = None
    stage: Optional[str] = None
    evidence_refs: Sequence[str] = field(default_factory=tuple)
    model_versions: Mapping[str, str] = field(default_factory=dict)
    config_version: Optional[str] = None
    code_version: Optional[str] = None
    source_timestamp: Optional[str] = None
    market_regime: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: str = field(default_factory=_utc_now_iso)
    shadow_only: bool = False

    def __post_init__(self) -> None:
        normalized = self.event_type.upper().strip()
        object.__setattr__(self, "event_type", normalized)
        object.__setattr__(self, "ticker", self.ticker.upper().strip())
        if normalized not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported decision event type: {normalized}")
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if not self.ticker:
            raise ValueError("ticker is required")
        if normalized == "COUNTERFACTUAL" and not self.shadow_only:
            raise ValueError("COUNTERFACTUAL events must be shadow_only=True")
        if self.shadow_only and normalized in {"PAPER_ORDER", "PAPER_FILL", "PAPER_CANCEL"}:
            raise ValueError("shadow events cannot represent executable portfolio mutations")

    def to_record(self) -> Dict[str, Any]:
        record = asdict(self)
        record["schema_version"] = "iios.decision-journal.v1"
        record["broker_connected"] = False
        record["live_execution"] = False
        return record


class DecisionJournal:
    """Append-only JSONL journal with explicit fsync durability.

    Existing bytes are never rewritten by this class. Each append is one JSON
    object followed by a newline, making the log auditable and recoverable.
    """

    def __init__(self, path: os.PathLike[str] | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: DecisionEvent) -> Dict[str, Any]:
        record = event.to_record()
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    def append_no_trade(
        self,
        *,
        case_id: str,
        ticker: str,
        reason: str,
        stage: str,
        score: Optional[float] = None,
        **metadata: Any,
    ) -> Dict[str, Any]:
        return self.append(DecisionEvent(
            case_id=case_id,
            ticker=ticker,
            event_type="NO_TRADE",
            decision="NO_TRADE",
            reason=reason,
            score=score,
            stage=stage,
            metadata=metadata,
        ))

    def append_counterfactual(
        self,
        *,
        case_id: str,
        ticker: str,
        reason: str,
        proposed_entry: Optional[float],
        proposed_stop: Optional[float],
        proposed_target: Optional[float],
        horizon: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(metadata or {})
        payload.update({
            "proposed_entry": proposed_entry,
            "proposed_stop": proposed_stop,
            "proposed_target": proposed_target,
            "horizon": horizon,
            "portfolio_effect": "NONE",
        })
        return self.append(DecisionEvent(
            case_id=case_id,
            ticker=ticker,
            event_type="COUNTERFACTUAL",
            decision="SHADOW_ONLY",
            reason=reason,
            metadata=payload,
            shadow_only=True,
        ))

    def read_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        records: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def unfinished_cases(self) -> Dict[str, Dict[str, Any]]:
        terminal = {"NO_TRADE", "REJECTED", "VETO", "PAPER_FILL", "PAPER_CANCEL"}
        latest: Dict[str, Dict[str, Any]] = {}
        for record in self.read_recent(limit=10000):
            latest[record["case_id"]] = record
        return {
            case_id: record
            for case_id, record in latest.items()
            if record.get("event_type") not in terminal
        }
