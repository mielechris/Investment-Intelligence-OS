import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from openai import OpenAI


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class RiskReviewStore:
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
                CREATE TABLE IF NOT EXISTS risk_reviews (
                    risk_review_id TEXT PRIMARY KEY,
                    escalation_id TEXT NOT NULL UNIQUE,
                    packet_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk_result_payload TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_risk_reviews_status ON risk_reviews(status, created_at ASC)"
            )

    def maybe_enqueue(self, *, escalation_row: dict, committee_result: dict) -> bool:
        if not bool(committee_result.get("risk_review_required", False)):
            return False
        packet = {
            "escalation_id": escalation_row["escalation_id"],
            "committee_packet": json.loads(escalation_row["packet_payload"]),
            "committee_result": committee_result,
            "paper_mode": True,
            "live_execution": False,
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO risk_reviews
                (risk_review_id, escalation_id, packet_payload, status, risk_result_payload, error, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (str(uuid4()), escalation_row["escalation_id"], json.dumps(packet), now, now),
            )
        return cursor.rowcount > 0

    def pending(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM risk_reviews WHERE status='pending' ORDER BY created_at ASC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM risk_reviews ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["packet"] = json.loads(item.pop("packet_payload"))
            raw = item.pop("risk_result_payload", None)
            item["risk_result"] = json.loads(raw) if raw else None
            output.append(item)
        return output

    def counts(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS count FROM risk_reviews GROUP BY status").fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {key: counts.get(key, 0) for key in ("pending", "running", "complete", "error")}

    def _mark(self, risk_review_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE risk_reviews SET status=?, risk_result_payload=?, error=?, updated_at=? WHERE risk_review_id=?",
                (status, json.dumps(result) if result is not None else None, error, now, risk_review_id),
            )

    def _run_risk_review(self, row: dict) -> dict:
        packet = json.loads(row["packet_payload"])
        client = OpenAI()
        prompt = f"""
You are the Risk Desk inside Investment Intelligence OS.

Review this committee research packet independently. Your job is not to find reasons to trade;
your job is to identify ways the paper thesis can fail, size uncertainty, and veto unsafe or under-evidenced setups.

RISK PACKET:
{json.dumps(packet, indent=2)}

Rules:
- PAPER MODE ONLY. Never authorize live execution or real capital.
- Evaluate liquidity, pricing uncertainty, concentration/control, dilution, governance, jurisdiction/regulatory risk,
  business solvency/going-concern risk, market-structure risk, downside scenarios, and missing data.
- A VETO is appropriate when evidence is insufficient to size risk responsibly or a hard risk boundary is triggered.
- WATCH_ONLY is allowed only when there are no hard vetoes and the evidence is sufficient for a bounded paper simulation.
- paper_execution_eligible may be true ONLY with WATCH_ONLY, no hard vetoes, and sufficient pricing/listing/liquidity/capitalization evidence.
- Real allowed_notional must remain 0 in this version. Paper simulation uses a separate fictional notional cap.

Return ONLY valid JSON:
{{
  "decision": "VETOED|WATCH_ONLY",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "headline": "string",
  "primary_risks": ["string"],
  "downside_scenarios": ["string"],
  "liquidity_assessment": "string",
  "concentration_assessment": "string",
  "sizing_constraints": ["string"],
  "hard_vetoes": ["string"],
  "missing_evidence": ["string"],
  "allowed_notional": 0,
  "confidence": 0.0,
  "paper_execution_eligible": false
}}
"""
        response = client.responses.create(model="gpt-5.6-luna", input=prompt)
        parsed = json.loads(response.output_text)
        if not isinstance(parsed, dict):
            raise ValueError("Risk output was not an object")

        decision = str(parsed.get("decision", "VETOED")).upper()
        if decision not in {"VETOED", "WATCH_ONLY"}:
            decision = "VETOED"
        parsed["decision"] = decision
        parsed["allowed_notional"] = 0

        hard_vetoes = parsed.get("hard_vetoes") or []
        eligible = bool(parsed.get("paper_execution_eligible", False))
        if decision != "WATCH_ONLY" or hard_vetoes:
            eligible = False
        parsed["paper_execution_eligible"] = eligible
        return parsed

    def process_pending(self, limit: int | None = None) -> dict:
        if not _bool_env("IIOS_AUTO_RUN_RISK", False):
            return {"enabled": False, "processed": 0, "message": "Set IIOS_AUTO_RUN_RISK=true to enable unattended risk reviews."}
        if limit is None:
            try:
                limit = max(1, min(int(os.getenv("IIOS_AUTO_RUN_RISK_MAX_PER_CYCLE", "3")), 20))
            except ValueError:
                limit = 3
        processed = 0
        errors = 0
        paper_candidates = 0
        for row in self.pending(limit=limit):
            self._mark(row["risk_review_id"], "running")
            try:
                result = self._run_risk_review(row)
                self._mark(row["risk_review_id"], "complete", result=result)
                from intelligence.paper_execution import paper_execution
                paper_candidates += int(paper_execution.maybe_enqueue(risk_row=row, risk_result=result))
                processed += 1
            except Exception as exc:
                self._mark(row["risk_review_id"], "error", error=str(exc))
                errors += 1
        return {"enabled": True, "processed": processed, "errors": errors, "paper_candidates": paper_candidates}


risk_reviews = RiskReviewStore()
