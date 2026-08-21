import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


class PaperPortfolioStore:
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
                CREATE TABLE IF NOT EXISTS paper_positions (
                    position_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    mark_price REAL NOT NULL,
                    simulated_notional REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    status TEXT NOT NULL,
                    thesis_payload TEXT NOT NULL,
                    synthetic_fixture INTEGER NOT NULL,
                    opened_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_marks (
                    mark_id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL,
                    mark_price REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )

    def record_simulated_order(self, *, candidate_id: str, order: dict, candidate_packet: dict) -> dict:
        simulated_notional = float(order.get("simulated_notional", 0) or 0)
        if simulated_notional <= 0:
            raise ValueError("Simulated order must have positive paper notional")

        risk_result = candidate_packet.get("risk_result", {})
        risk_packet = candidate_packet.get("risk_packet", {})
        synthetic = bool(order.get("synthetic_fixture", False) or risk_result.get("synthetic_fixture", False))
        market_data = risk_packet.get("market_data", {}) if isinstance(risk_packet, dict) else {}
        symbol = str(market_data.get("symbol") or ("IIOS-TEST" if synthetic else "UNRESOLVED")).upper()
        entry_price = float(market_data.get("entry_price") or (100.0 if synthetic else 1.0))
        side = str(market_data.get("side") or "LONG").upper()
        if side not in {"LONG", "SHORT"}:
            side = "LONG"
        quantity = simulated_notional / entry_price
        now = datetime.now(timezone.utc).isoformat()
        thesis = {
            "risk_result": risk_result,
            "risk_packet": risk_packet,
            "source_risk_review_id": order.get("source_risk_review_id"),
            "paper_mode": True,
            "real_capital": 0,
        }

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO paper_positions
                (position_id, candidate_id, symbol, side, quantity, entry_price, mark_price,
                 simulated_notional, unrealized_pnl, realized_pnl, status, thesis_payload,
                 synthetic_fixture, opened_at, updated_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'open', ?, ?, ?, ?, NULL)
                """,
                (
                    str(uuid4()), candidate_id, symbol, side, quantity, entry_price, entry_price,
                    simulated_notional, json.dumps(thesis), int(synthetic), now, now,
                ),
            )
        return self.by_candidate(candidate_id)

    def by_candidate(self, candidate_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_positions WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise KeyError("Paper position not found")
        return self._decode(dict(row))

    def mark(self, position_id: str, mark_price: float, *, source: str = "manual") -> dict:
        mark_price = float(mark_price)
        if mark_price <= 0:
            raise ValueError("mark_price must be positive")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM paper_positions WHERE position_id=?", (position_id,)).fetchone()
            if row is None:
                raise KeyError("Paper position not found")
            direction = 1.0 if row["side"] == "LONG" else -1.0
            unrealized = (mark_price - float(row["entry_price"])) * float(row["quantity"]) * direction
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "UPDATE paper_positions SET mark_price=?, unrealized_pnl=?, updated_at=? WHERE position_id=?",
                (mark_price, unrealized, now, position_id),
            )
            connection.execute(
                "INSERT INTO paper_marks (mark_id, position_id, mark_price, unrealized_pnl, source, observed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), position_id, mark_price, unrealized, source, now),
            )
        return self.get(position_id)

    def get(self, position_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM paper_positions WHERE position_id=?", (position_id,)).fetchone()
        if row is None:
            raise KeyError("Paper position not found")
        return self._decode(dict(row))

    def recent(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_positions ORDER BY opened_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._decode(dict(row)) for row in rows]

    def summary(self) -> dict:
        positions = self.recent(limit=500)
        open_positions = [item for item in positions if item["status"] == "open"]
        return {
            "positions": len(positions),
            "open_positions": len(open_positions),
            "simulated_notional": round(sum(float(item["simulated_notional"]) for item in open_positions), 2),
            "unrealized_pnl": round(sum(float(item["unrealized_pnl"]) for item in open_positions), 2),
            "realized_pnl": round(sum(float(item["realized_pnl"]) for item in positions), 2),
            "real_capital": 0,
            "paper_mode": True,
        }

    @staticmethod
    def _decode(item: dict) -> dict:
        item["thesis"] = json.loads(item.pop("thesis_payload"))
        item["synthetic_fixture"] = bool(item.get("synthetic_fixture"))
        return item


paper_portfolio = PaperPortfolioStore()
