import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from openai import OpenAI

from factory.store import agents
from factory.system_agents import MARKET_HISTORY_AGENT_ID


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


def _auto_enabled() -> bool:
    explicit = os.getenv("IIOS_AUTO_RUN_POSTMORTEMS")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    inherited = os.getenv("IIOS_AUTO_RUN_AGENTS", "false")
    return inherited.strip().lower() in {"1", "true", "yes", "on"}


class PostmortemIntelligenceStore:
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
                CREATE TABLE IF NOT EXISTS history_postmortem_jobs (
                    job_id TEXT PRIMARY KEY,
                    review_id TEXT NOT NULL UNIQUE,
                    review_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_payload TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_postmortem_status
                ON history_postmortem_jobs(status, created_at ASC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS history_pattern_library (
                    pattern_id TEXT PRIMARY KEY,
                    review_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    return_pct REAL NOT NULL,
                    headline TEXT NOT NULL,
                    tags_payload TEXT NOT NULL,
                    lesson_payload TEXT NOT NULL,
                    synthetic_fixture INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_patterns_symbol
                ON history_pattern_library(symbol, created_at DESC)
                """
            )

    def maybe_enqueue(self, *, review_id: str, review: dict) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO history_postmortem_jobs
                (job_id, review_id, review_payload, status, result_payload, error, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?)
                """,
                (str(uuid4()), review_id, json.dumps(review), now, now),
            )
        return cursor.rowcount > 0

    def pending(self, limit: int = 25) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM history_postmortem_jobs WHERE status='pending' ORDER BY created_at ASC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM history_postmortem_jobs GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {key: counts.get(key, 0) for key in ("pending", "running", "complete", "error")}

    def recent_jobs(self, limit: int = 50) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM history_postmortem_jobs ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 250)),),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["review"] = json.loads(item.pop("review_payload"))
            raw = item.pop("result_payload", None)
            item["result"] = json.loads(raw) if raw else None
            output.append(item)
        return output

    def recent_patterns(self, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM history_pattern_library ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._decode_pattern(dict(row)) for row in rows]

    def search_patterns(self, query: str, limit: int = 50) -> list[dict]:
        query = query.strip()
        if not query:
            return self.recent_patterns(limit=limit)
        needle = f"%{query.lower()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM history_pattern_library
                WHERE lower(symbol) LIKE ?
                   OR lower(outcome) LIKE ?
                   OR lower(headline) LIKE ?
                   OR lower(tags_payload) LIKE ?
                   OR lower(lesson_payload) LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (needle, needle, needle, needle, needle, max(1, min(limit, 200))),
            ).fetchall()
        return [self._decode_pattern(dict(row)) for row in rows]

    def _mark(self, job_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE history_postmortem_jobs
                SET status=?, result_payload=?, error=?, updated_at=?
                WHERE job_id=?
                """,
                (status, json.dumps(result) if result is not None else None, error, now, job_id),
            )

    def _run_history_review(self, row: dict) -> dict:
        review = json.loads(row["review_payload"])
        agent = agents.get(MARKET_HISTORY_AGENT_ID)
        if agent is None or agent.status != "approved":
            raise RuntimeError("Market History & Regime Analyst is not approved")

        synthetic = bool(review.get("synthetic_fixture", False))
        client = OpenAI()
        prompt = f"""
You are {agent.name} inside Investment Intelligence OS.

MISSION:
{agent.mission}

A PAPER position has closed. Perform a postmortem that improves future reasoning without rewriting history.

CLOSED OUTCOME RECORD:
{json.dumps(review, indent=2)}

Rules:
- PAPER MODE ONLY. No live execution or real-money recommendation.
- Use only the supplied closed-outcome record for factual claims about this trade.
- Distinguish what the realized return actually demonstrates from what remains causally unknown.
- Do not infer why price moved unless evidence in the record supports that mechanism.
- Compare the original risk/thesis framing with the observed outcome.
- Explicitly identify hindsight traps and alternative explanations.
- Reusable patterns must be conditional, falsifiable, and framed as hypotheses rather than laws.
- A winning trade can still contain bad reasoning; a losing trade can still contain good reasoning.
- If this is a synthetic fixture, DO NOT derive any real-market lesson. Restrict reusable lessons to system/process validation.
- Confidence must be 0.0 to 1.0.

Synthetic fixture: {synthetic}

Return ONLY valid JSON with exactly these fields:
{{
  "headline": "string",
  "thesis_assessment": "SUPPORTED|PARTIAL|REFUTED|INSUFFICIENT_EVIDENCE",
  "outcome_interpretation": "string",
  "what_worked": ["string"],
  "what_failed": ["string"],
  "signals_that_mattered": ["string"],
  "risks_overstated": ["string"],
  "risks_understated": ["string"],
  "causal_unknowns": ["string"],
  "hindsight_traps": ["string"],
  "regime_tags": ["string"],
  "reusable_patterns": ["string"],
  "anti_patterns": ["string"],
  "next_time_rules": ["string"],
  "confidence": 0.0
}}
"""
        response = client.responses.create(model=agent.model, input=prompt)
        parsed = json.loads(response.output_text)
        if not isinstance(parsed, dict):
            raise ValueError("Postmortem output was not an object")
        try:
            parsed["confidence"] = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
        except (TypeError, ValueError):
            parsed["confidence"] = 0.5
        parsed["synthetic_fixture"] = synthetic
        parsed["paper_mode"] = True
        parsed["real_capital"] = 0
        return parsed

    def _save_pattern(self, *, review_id: str, review: dict, result: dict) -> None:
        tags = list(result.get("regime_tags") or [])
        tags.extend([review.get("outcome", "UNKNOWN"), review.get("side", "UNKNOWN")])
        if review.get("synthetic_fixture"):
            tags.append("SYNTHETIC_FIXTURE")
        tags = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO history_pattern_library
                (pattern_id, review_id, symbol, outcome, return_pct, headline,
                 tags_payload, lesson_payload, synthetic_fixture, created_at)
                VALUES (
                    COALESCE((SELECT pattern_id FROM history_pattern_library WHERE review_id=?), ?),
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    review_id,
                    str(uuid4()),
                    review_id,
                    str(review.get("symbol") or "UNKNOWN"),
                    str(review.get("outcome") or "UNKNOWN"),
                    float(review.get("return_pct", 0.0) or 0.0),
                    str(result.get("headline") or "Postmortem lesson"),
                    json.dumps(tags),
                    json.dumps(result),
                    int(bool(review.get("synthetic_fixture", False))),
                    now,
                ),
            )

    def process_pending(self, limit: int | None = None) -> dict:
        if not _auto_enabled():
            return {
                "enabled": False,
                "processed": 0,
                "message": "Enable IIOS_AUTO_RUN_POSTMORTEMS or IIOS_AUTO_RUN_AGENTS to process postmortems.",
            }
        if limit is None:
            try:
                limit = max(1, min(int(os.getenv("IIOS_AUTO_RUN_POSTMORTEMS_MAX_PER_CYCLE", "2")), 10))
            except ValueError:
                limit = 2

        processed = 0
        errors = 0
        for row in self.pending(limit=limit):
            self._mark(row["job_id"], "running")
            try:
                review = json.loads(row["review_payload"])
                result = self._run_history_review(row)
                self._save_pattern(review_id=row["review_id"], review=review, result=result)
                self._mark(row["job_id"], "complete", result=result)
                processed += 1
            except Exception as exc:
                self._mark(row["job_id"], "error", error=str(exc))
                errors += 1
        return {"enabled": True, "processed": processed, "errors": errors}

    @staticmethod
    def _decode_pattern(item: dict) -> dict:
        item["tags"] = json.loads(item.pop("tags_payload"))
        item["lesson"] = json.loads(item.pop("lesson_payload"))
        item["synthetic_fixture"] = bool(item.get("synthetic_fixture"))
        return item


postmortem_intelligence = PostmortemIntelligenceStore()
