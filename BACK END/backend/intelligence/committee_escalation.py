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


class CommitteeEscalationStore:
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
                CREATE TABLE IF NOT EXISTS committee_escalations (
                    escalation_id TEXT PRIMARY KEY,
                    dispatch_id TEXT NOT NULL UNIQUE,
                    agent_id TEXT NOT NULL,
                    materiality TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    packet_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    committee_result_payload TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_committee_escalations_status
                ON committee_escalations(status, created_at ASC)
                """
            )

    def maybe_enqueue(self, *, dispatch_row: dict, result: dict) -> bool:
        materiality = str(result.get("materiality", "LOW")).upper()
        try:
            confidence = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        threshold = float(os.getenv("IIOS_COMMITTEE_CONFIDENCE_THRESHOLD", "0.70"))
        requested = bool(result.get("committee_escalation", False))
        if materiality != "HIGH" or confidence < threshold or not requested:
            return False

        packet = {
            "dispatch_id": dispatch_row["dispatch_id"],
            "agent_id": dispatch_row["agent_id"],
            "route_reason": dispatch_row["route_reason"],
            "evidence": json.loads(dispatch_row["evidence_payload"]),
            "agent_result": result,
            "paper_mode": True,
            "live_execution": False,
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO committee_escalations
                (escalation_id, dispatch_id, agent_id, materiality, confidence,
                 packet_payload, status, committee_result_payload, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (
                    str(uuid4()),
                    dispatch_row["dispatch_id"],
                    dispatch_row["agent_id"],
                    materiality,
                    confidence,
                    json.dumps(packet),
                    now,
                    now,
                ),
            )
        return cursor.rowcount > 0

    def pending(self, limit: int = 50) -> list[dict]:
        limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM committee_escalations
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM committee_escalations
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        output: list[dict] = []
        for row in rows:
            item = dict(row)
            item["packet"] = json.loads(item.pop("packet_payload"))
            if item.get("committee_result_payload"):
                item["committee_result"] = json.loads(item.pop("committee_result_payload"))
            else:
                item.pop("committee_result_payload", None)
                item["committee_result"] = None
            output.append(item)
        return output

    def counts(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM committee_escalations GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "complete": counts.get("complete", 0),
            "error": counts.get("error", 0),
        }

    def _mark(self, escalation_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE committee_escalations
                SET status = ?, committee_result_payload = ?, error = ?, updated_at = ?
                WHERE escalation_id = ?
                """,
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    error,
                    now,
                    escalation_id,
                ),
            )

    def _run_committee(self, row: dict) -> dict:
        packet = json.loads(row["packet_payload"])
        client = OpenAI()
        prompt = f"""
You are the Investment Committee Chair inside Investment Intelligence OS.

A specialist agent escalated a HIGH-materiality event. Review the evidence and specialist analysis
without assuming the specialist is correct. Preserve uncertainty and explicitly challenge weak causal claims.

COMMITTEE PACKET:
{json.dumps(packet, indent=2)}

Rules:
- PAPER MODE ONLY.
- Do not authorize capital or live execution.
- Use only the supplied evidence for current factual claims.
- Identify the strongest supporting argument and strongest objection.
- If evidence is incomplete, keep the decision at WATCH or NO_TRADE.
- Confidence must be 0.0 to 1.0.

Return ONLY valid JSON:
{{
  "headline": "string",
  "summary": "string",
  "support": "string",
  "dissent": "string",
  "missing_evidence": ["string"],
  "confidence": 0.0,
  "disposition": "WATCH|NO_TRADE",
  "risk_review_required": true
}}
"""
        response = client.responses.create(model="gpt-5.6-luna", input=prompt)
        parsed = json.loads(response.output_text)
        if not isinstance(parsed, dict):
            raise ValueError("Committee output was not an object")
        return parsed

    def process_pending(self, limit: int | None = None) -> dict:
        if not _bool_env("IIOS_AUTO_RUN_COMMITTEE", False):
            return {
                "enabled": False,
                "processed": 0,
                "message": "Set IIOS_AUTO_RUN_COMMITTEE=true to enable unattended committee model calls.",
            }

        if limit is None:
            try:
                limit = max(1, min(int(os.getenv("IIOS_AUTO_RUN_COMMITTEE_MAX_PER_CYCLE", "3")), 20))
            except ValueError:
                limit = 3

        processed = 0
        errors = 0
        for row in self.pending(limit=limit):
            escalation_id = row["escalation_id"]
            self._mark(escalation_id, "running")
            try:
                result = self._run_committee(row)
                self._mark(escalation_id, "complete", result=result)
                processed += 1
            except Exception as exc:
                self._mark(escalation_id, "error", error=str(exc))
                errors += 1
        return {"enabled": True, "processed": processed, "errors": errors}


committee_escalations = CommitteeEscalationStore()
