import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Generic, TypeVar

from pydantic import BaseModel

from factory.models import AgentDefinition, InterviewInsightPacket, InterviewSession


ModelT = TypeVar("ModelT", bound=BaseModel)


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()

    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


class SQLiteJsonStore(Generic[ModelT]):
    """Small persistent repository that preserves the old dict-like API."""

    def __init__(
        self,
        table_name: str,
        model_type: type[ModelT],
        key_field: str,
        database_path: Path | None = None,
    ) -> None:
        self.table_name = table_name
        self.model_type = model_type
        self.key_field = key_field
        self.database_path = database_path or _database_path()
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    record_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def get(self, key: str, default: ModelT | None = None) -> ModelT | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"SELECT payload FROM {self.table_name} WHERE record_key = ?",
                (key,),
            ).fetchone()

        if row is None:
            return default
        return self.model_type.model_validate_json(row[0])

    def values(self) -> list[ModelT]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM {self.table_name} ORDER BY updated_at ASC"
            ).fetchall()
        return [self.model_type.model_validate_json(row[0]) for row in rows]

    def save(self, model: ModelT) -> ModelT:
        key = str(getattr(model, self.key_field))
        now = datetime.now(timezone.utc).isoformat()
        payload = model.model_dump_json()

        with self._lock, self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {self.table_name} (record_key, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(record_key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (key, payload, now),
            )
        return model

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(f"DELETE FROM {self.table_name}")

    def __len__(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM {self.table_name}"
            ).fetchone()
        return int(row[0]) if row else 0


interviews = SQLiteJsonStore(
    table_name="factory_interviews",
    model_type=InterviewSession,
    key_field="id",
)
insight_packets = SQLiteJsonStore(
    table_name="factory_insight_packets",
    model_type=InterviewInsightPacket,
    key_field="interview_id",
)
agents = SQLiteJsonStore(
    table_name="factory_agents",
    model_type=AgentDefinition,
    key_field="id",
)


def save_interview(interview: InterviewSession) -> InterviewSession:
    interview.updated_at = datetime.now(timezone.utc)
    return interviews.save(interview)


def save_insight_packet(packet: InterviewInsightPacket) -> InterviewInsightPacket:
    return insight_packets.save(packet)


def save_agent(agent: AgentDefinition) -> AgentDefinition:
    return agents.save(agent)
