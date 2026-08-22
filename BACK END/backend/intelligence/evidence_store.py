import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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


class EvidenceStore:
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
                CREATE TABLE IF NOT EXISTS intelligence_evidence (
                    evidence_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_observed_at
                ON intelligence_evidence(observed_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_kind
                ON intelligence_evidence(source_kind, observed_at DESC)
                """
            )

    def save(self, item: EvidenceItem) -> bool:
        key = _evidence_key(item)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO intelligence_evidence
                (evidence_key, payload, source_kind, source_name, observed_at, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    item.model_dump_json(),
                    item.source_kind,
                    item.source_name,
                    item.observed_at.isoformat(),
                    now,
                ),
            )
        return cursor.rowcount > 0

    def save_many(self, items: list[EvidenceItem]) -> int:
        return sum(1 for item in items if self.save(item))

    def recent(self, *, limit: int = 100, source_kind: str | None = None) -> list[EvidenceItem]:
        limit = max(1, min(limit, 1000))
        with self._connect() as connection:
            if source_kind:
                rows = connection.execute(
                    """
                    SELECT payload FROM intelligence_evidence
                    WHERE source_kind = ?
                    ORDER BY observed_at DESC
                    LIMIT ?
                    """,
                    (source_kind, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload FROM intelligence_evidence
                    ORDER BY observed_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [EvidenceItem.model_validate_json(row["payload"]) for row in rows]

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM intelligence_evidence").fetchone()
        return int(row["count"]) if row else 0


evidence_store = EvidenceStore()
