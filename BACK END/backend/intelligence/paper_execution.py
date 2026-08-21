import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from intelligence.paper_portfolio import paper_portfolio


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


def _paper_notional_cap() -> float:
    try:
        return max(0.0, min(float(os.getenv("IIOS_MAX_PAPER_NOTIONAL", "10000")), 1_000_000.0))
    except ValueError:
        return 10000.0


class PaperExecutionStore:
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
                CREATE TABLE IF NOT EXISTS paper_execution_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    risk_review_id TEXT NOT NULL UNIQUE,
                    packet_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    simulated_order_payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def maybe_enqueue(self, *, risk_row: dict, risk_result: dict) -> bool:
        decision = str(risk_result.get("decision", "VETOED")).upper()
        eligible = bool(risk_result.get("paper_execution_eligible", False))
        hard_vetoes = risk_result.get("hard_vetoes") or []
        if decision != "WATCH_ONLY" or not eligible or hard_vetoes:
            return False

        packet = {
            "risk_review_id": risk_row["risk_review_id"],
            "risk_packet": json.loads(risk_row["packet_payload"]),
            "risk_result": risk_result,
            "paper_mode": True,
            "live_execution": False,
            "real_capital_authorized": 0,
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO paper_execution_candidates
                (candidate_id, risk_review_id, packet_payload, status, simulated_order_payload, created_at, updated_at)
                VALUES (?, ?, ?, 'ready', NULL, ?, ?)
                """,
                (str(uuid4()), risk_row["risk_review_id"], json.dumps(packet), now, now),
            )
        return cursor.rowcount > 0

    def create_controlled_test_candidate(self) -> dict:
        risk_review_id = "synthetic-controlled-paper-readiness-v1"
        synthetic_packet = {
            "fixture": True,
            "fixture_name": "Controlled Paper Readiness Test",
            "synthetic": True,
            "description": "Deterministic test data used only to verify Risk-to-Paper handoff.",
            "market_data": {
                "symbol": "IIOS-TEST",
                "side": "LONG",
                "entry_price": 100.0,
                "listing_confirmed": True,
                "pricing_confirmed": True,
                "liquidity_confirmed": True,
                "capitalization_confirmed": True,
            },
            "paper_mode": True,
            "live_execution": False,
            "real_security": False,
        }
        synthetic_risk_result = {
            "decision": "WATCH_ONLY",
            "risk_level": "LOW",
            "headline": "CONTROLLED TEST: synthetic case cleared for paper simulation",
            "primary_risks": ["Synthetic test fixture only; no real security or market exposure."],
            "downside_scenarios": ["Simulation result has no investment meaning."],
            "liquidity_assessment": "Synthetic liquidity assumption marked confirmed for gate testing.",
            "concentration_assessment": "No real portfolio concentration exists; fixture is simulation-only.",
            "sizing_constraints": ["Simulated notional capped by IIOS_MAX_PAPER_NOTIONAL.", "Real notional must remain zero."],
            "hard_vetoes": [],
            "missing_evidence": [],
            "allowed_notional": 0,
            "confidence": 1.0,
            "paper_execution_eligible": True,
            "synthetic_fixture": True,
        }
        risk_row = {"risk_review_id": risk_review_id, "packet_payload": json.dumps(synthetic_packet)}
        created = self.maybe_enqueue(risk_row=risk_row, risk_result=synthetic_risk_result)
        candidates = [item for item in self.recent(limit=100) if item["risk_review_id"] == risk_review_id]
        return {
            "created": created,
            "candidate": candidates[0] if candidates else None,
            "synthetic": True,
            "paper_mode": True,
            "live_execution": False,
            "real_capital_authorized": 0,
        }

    def recent(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM paper_execution_candidates ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["packet"] = json.loads(item.pop("packet_payload"))
            raw = item.pop("simulated_order_payload", None)
            item["simulated_order"] = json.loads(raw) if raw else None
            output.append(item)
        return output

    def counts(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM paper_execution_candidates GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {"ready": counts.get("ready", 0), "simulated": counts.get("simulated", 0)}

    def simulate(self, candidate_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_execution_candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise KeyError("Paper execution candidate not found")
        packet = json.loads(row["packet_payload"])
        if row["status"] == "simulated" and row["simulated_order_payload"]:
            order = json.loads(row["simulated_order_payload"])
            try:
                paper_portfolio.record_simulated_order(candidate_id=candidate_id, order=order, candidate_packet=packet)
            except Exception:
                pass
            return order

        risk_result = packet.get("risk_result", {})
        if str(risk_result.get("decision", "VETOED")).upper() != "WATCH_ONLY" or not risk_result.get("paper_execution_eligible"):
            raise RuntimeError("Risk review does not authorize paper simulation")
        if risk_result.get("hard_vetoes"):
            raise RuntimeError("Hard risk veto prevents paper simulation")

        simulated_notional = _paper_notional_cap()
        order = {
            "execution": "PAPER_ORDER_SIMULATED",
            "simulated_notional": simulated_notional,
            "real_notional": 0,
            "broker_order_sent": False,
            "live_execution": False,
            "paper_mode": True,
            "synthetic_fixture": bool(risk_result.get("synthetic_fixture", False)),
            "source_risk_review_id": row["risk_review_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE paper_execution_candidates SET status='simulated', simulated_order_payload=?, updated_at=? WHERE candidate_id=?",
                (json.dumps(order), now, candidate_id),
            )
        position = paper_portfolio.record_simulated_order(candidate_id=candidate_id, order=order, candidate_packet=packet)
        return {**order, "position_id": position["position_id"]}


paper_execution = PaperExecutionStore()
