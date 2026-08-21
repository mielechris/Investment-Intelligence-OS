import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from openai import OpenAI

from factory.store import agents
from factory.system_agents import IPO_AGENT_ID, MARKET_HISTORY_AGENT_ID
from intelligence.models import EvidenceItem


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


def _evidence_key(item: EvidenceItem) -> str:
    identity = "|".join(
        [
            item.source_name,
            item.source_kind,
            item.url or "",
            item.title,
            item.published_at.isoformat() if item.published_at else "",
            item.summary,
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class EventDispatcher:
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
                CREATE TABLE IF NOT EXISTS intelligence_dispatch_queue (
                    dispatch_id TEXT PRIMARY KEY,
                    evidence_key TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    route_reason TEXT NOT NULL,
                    evidence_payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_payload TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(evidence_key, agent_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dispatch_status_created
                ON intelligence_dispatch_queue(status, created_at ASC)
                """
            )

    def route(self, item: EvidenceItem) -> list[tuple[str, str]]:
        text = f"{item.source_name} {item.title} {item.summary}".lower()
        routes: list[tuple[str, str]] = []

        ipo_markers = ("s-1", "f-1", "424b4", "effect", "ipo-related", "initial public offering")
        if "sec edgar" in text and any(marker in text for marker in ipo_markers):
            routes.append((IPO_AGENT_ID, "IPO-related SEC filing"))

        if item.source_kind in {"market", "macro"}:
            routes.append((MARKET_HISTORY_AGENT_ID, f"{item.source_kind} evidence can inform regime history"))
        elif item.source_kind == "company" and "sec edgar" in text:
            routes.append((MARKET_HISTORY_AGENT_ID, "SEC company event can inform historical event studies"))

        # Dynamic approved agents may opt into broad evidence classes through feed identifiers.
        feed_tokens = {
            "market": {"equity_market", "equity_market_history", "market_prices", "crypto_market"},
            "macro": {"fred_macro", "macro"},
            "policy": {"policy", "policy_history"},
            "company": {"sec_company", "company_fundamentals", "sec_edgar_ipo"},
            "commodity": {"commodity", "commodities"},
            "weather": {"weather", "agriculture_weather"},
            "geopolitical": {"geopolitical", "geopolitics"},
        }
        acceptable = feed_tokens.get(item.source_kind, set())
        for agent in agents.values():
            if agent.status != "approved" or agent.id in {IPO_AGENT_ID, MARKET_HISTORY_AGENT_ID}:
                continue
            configured = {feed.lower() for feed in agent.data_feeds}
            if configured.intersection(acceptable):
                routes.append((agent.id, f"Approved agent subscribes to {item.source_kind} evidence"))

        deduped: dict[str, str] = {}
        for agent_id, reason in routes:
            deduped.setdefault(agent_id, reason)
        return list(deduped.items())

    def enqueue(self, items: list[EvidenceItem]) -> int:
        inserted = 0
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            for item in items:
                evidence_key = _evidence_key(item)
                for agent_id, reason in self.route(item):
                    agent = agents.get(agent_id)
                    if agent is None or agent.status != "approved":
                        continue
                    cursor = connection.execute(
                        """
                        INSERT OR IGNORE INTO intelligence_dispatch_queue
                        (dispatch_id, evidence_key, agent_id, route_reason, evidence_payload,
                         status, result_payload, error, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            evidence_key,
                            agent_id,
                            reason,
                            item.model_dump_json(),
                            now,
                            now,
                        ),
                    )
                    inserted += int(cursor.rowcount > 0)
        return inserted

    def pending(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(limit, 1000))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM intelligence_dispatch_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(limit, 1000))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM intelligence_dispatch_queue
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_payload"))
            if item.get("result_payload"):
                item["result"] = json.loads(item.pop("result_payload"))
            else:
                item.pop("result_payload", None)
                item["result"] = None
            output.append(item)
        return output

    def counts(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM intelligence_dispatch_queue GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {
            "pending": counts.get("pending", 0),
            "running": counts.get("running", 0),
            "complete": counts.get("complete", 0),
            "error": counts.get("error", 0),
        }

    def _mark(self, dispatch_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE intelligence_dispatch_queue
                SET status = ?, result_payload = ?, error = ?, updated_at = ?
                WHERE dispatch_id = ?
                """,
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    error,
                    now,
                    dispatch_id,
                ),
            )

    def _run_agent(self, row: dict) -> dict:
        agent = agents.get(row["agent_id"])
        if agent is None or agent.status != "approved":
            raise RuntimeError("Dispatch target is not an approved agent")

        evidence = json.loads(row["evidence_payload"])
        client = OpenAI()
        prompt = f"""
You are {agent.name}, an approved specialist agent inside Investment Intelligence OS.

ROLE: {agent.role}
MISSION: {agent.mission}
INSTRUCTIONS: {agent.instructions}
RISK BOUNDARIES: {json.dumps(agent.risk_boundaries)}
ROUTE REASON: {row['route_reason']}

NEW EVIDENCE EVENT:
{json.dumps(evidence, indent=2)}

Analyze whether this new evidence materially changes anything worth escalating.
Use only supplied evidence for current factual claims. Identify missing evidence.
This is PAPER MODE only. Do not authorize capital or recommend a real-money trade.
Return ONLY valid JSON with:
{{
  "materiality": "HIGH|MEDIUM|LOW|IGNORE",
  "headline": "string",
  "view": "string",
  "mechanism": "string",
  "missing_evidence": ["string"],
  "committee_escalation": true,
  "confidence": 0.0,
  "disposition": "WATCH|NO_TRADE"
}}
"""
        response = client.responses.create(model=agent.model, input=prompt)
        try:
            parsed = json.loads(response.output_text)
            if not isinstance(parsed, dict):
                raise ValueError("Agent output was not an object")
            return parsed
        except (json.JSONDecodeError, ValueError, TypeError):
            return {
                "materiality": "LOW",
                "headline": f"{agent.name} reviewed new evidence",
                "view": response.output_text,
                "mechanism": "Unstructured model response",
                "missing_evidence": agent.evidence_requirements,
                "committee_escalation": False,
                "confidence": 0.4,
                "disposition": "NO_TRADE",
            }

    def process_pending(self, limit: int | None = None) -> dict:
        if not _bool_env("IIOS_AUTO_RUN_AGENTS", False):
            return {"enabled": False, "processed": 0, "message": "Set IIOS_AUTO_RUN_AGENTS=true to enable unattended model calls."}

        if limit is None:
            try:
                limit = max(1, min(int(os.getenv("IIOS_AUTO_RUN_MAX_PER_CYCLE", "5")), 50))
            except ValueError:
                limit = 5

        rows = self.pending(limit=limit)
        processed = 0
        errors = 0
        for row in rows:
            dispatch_id = row["dispatch_id"]
            self._mark(dispatch_id, "running")
            try:
                result = self._run_agent(row)
                self._mark(dispatch_id, "complete", result=result)
                processed += 1
            except Exception as exc:
                self._mark(dispatch_id, "error", error=str(exc))
                errors += 1
        return {"enabled": True, "processed": processed, "errors": errors}


dispatcher = EventDispatcher()
