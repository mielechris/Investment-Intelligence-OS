import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from intelligence.dispatcher import dispatcher
from intelligence.evidence_store import evidence_store
from intelligence.models import EvidenceItem


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


class OutcomeLearningStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or _database_path()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_outcome_reviews (
                    review_id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL UNIQUE,
                    outcome TEXT NOT NULL,
                    return_pct REAL NOT NULL,
                    review_payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_from_closed_position(self, position: dict) -> dict:
        if position.get("status") != "closed":
            raise ValueError("Outcome review requires a closed paper position")

        position_id = str(position["position_id"])
        existing = self.by_position(position_id)
        if existing is not None:
            return {**existing, "created": False, "history_dispatches": 0}

        notional = float(position.get("simulated_notional", 0) or 0)
        realized = float(position.get("realized_pnl", 0) or 0)
        return_pct = (realized / notional * 100.0) if notional else 0.0
        if realized > 0.005:
            outcome = "WIN"
        elif realized < -0.005:
            outcome = "LOSS"
        else:
            outcome = "FLAT"

        thesis = position.get("thesis") or {}
        risk_result = thesis.get("risk_result") if isinstance(thesis, dict) else {}
        review = {
            "position_id": position_id,
            "symbol": position.get("symbol"),
            "side": position.get("side"),
            "outcome": outcome,
            "entry_price": position.get("entry_price"),
            "exit_price": position.get("mark_price"),
            "quantity": position.get("quantity"),
            "simulated_notional": notional,
            "realized_pnl": realized,
            "return_pct": round(return_pct, 4),
            "opened_at": position.get("opened_at"),
            "closed_at": position.get("closed_at"),
            "synthetic_fixture": bool(position.get("synthetic_fixture", False)),
            "original_risk_decision": (risk_result or {}).get("decision") if isinstance(risk_result, dict) else None,
            "original_risk_level": (risk_result or {}).get("risk_level") if isinstance(risk_result, dict) else None,
            "original_risk_headline": (risk_result or {}).get("headline") if isinstance(risk_result, dict) else None,
            "thesis_snapshot": thesis,
            "paper_mode": True,
            "real_capital": 0,
        }
        now = datetime.now(timezone.utc).isoformat()
        review_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_outcome_reviews
                (review_id, position_id, outcome, return_pct, review_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (review_id, position_id, outcome, return_pct, json.dumps(review), now),
            )

        evidence = EvidenceItem(
            source_name="IIOS Outcome Ledger",
            source_kind="market",
            title=f"Paper outcome: {position.get('symbol')} {outcome} {return_pct:+.2f}%",
            published_at=datetime.fromisoformat(position["closed_at"]) if position.get("closed_at") else datetime.now(timezone.utc),
            observed_at=datetime.now(timezone.utc),
            summary=(
                f"Closed paper position {position.get('symbol')} {position.get('side')} at "
                f"{position.get('mark_price')}; entry {position.get('entry_price')}; realized P&L "
                f"{realized:+.2f} on simulated notional {notional:.2f} ({return_pct:+.2f}%). "
                f"Outcome={outcome}. Original risk decision={(risk_result or {}).get('decision') if isinstance(risk_result, dict) else None}. "
                f"Synthetic fixture={bool(position.get('synthetic_fixture', False))}. Real capital=0."
            ),
            freshness="fresh",
            confidence=1.0,
        )
        inserted = evidence_store.save(evidence)
        history_dispatches = dispatcher.enqueue([evidence]) if inserted else 0

        return {
            "review_id": review_id,
            "review": review,
            "created": True,
            "evidence_inserted": inserted,
            "history_dispatches": history_dispatches,
        }

    def by_position(self, position_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_outcome_reviews WHERE position_id=?", (position_id,)
            ).fetchone()
        if row is None:
            return None
        return self._decode(dict(row))

    def recent(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_outcome_reviews ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._decode(dict(row)) for row in rows]

    @staticmethod
    def _decode(item: dict) -> dict:
        item["review"] = json.loads(item.pop("review_payload"))
        return item


outcome_learning = OutcomeLearningStore()
