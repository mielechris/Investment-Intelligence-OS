import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "iios_ledger.db"
DB_PATH = Path(os.getenv("IIOS_DB_PATH", str(DEFAULT_DB_PATH)))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    """
    Transactional SQLite connection that is always closed.

    sqlite3.Connection.__exit__ commits/rolls back but does not
    close the underlying connection, so ledger access needs an
    explicit lifecycle wrapper.
    """
    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        "PRAGMA journal_mode=WAL"
    )
    connection.execute(
        "PRAGMA foreign_keys=ON"
    )

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_ledger() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger_objects (
                object_id TEXT PRIMARY KEY,
                object_type TEXT NOT NULL,
                case_id TEXT NOT NULL,
                parent_id TEXT,
                topic TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ledger_case
                ON ledger_objects(case_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_ledger_type
                ON ledger_objects(object_type, created_at);
            CREATE INDEX IF NOT EXISTS idx_ledger_topic
                ON ledger_objects(topic, created_at);

            CREATE TABLE IF NOT EXISTS risk_authorization_state (
                authorization_id TEXT PRIMARY KEY,
                consumed INTEGER NOT NULL DEFAULT 0,
                consumed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS paper_authorization_state (
                authorization_id TEXT PRIMARY KEY,
                consumed INTEGER NOT NULL DEFAULT 0,
                consumed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                entity_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_case
                ON audit_events(case_id, created_at);
            """
        )


def record_object(
    object_id: str,
    object_type: str,
    case_id: str,
    payload: dict[str, Any],
    *,
    parent_id: str | None = None,
    topic: str | None = None,
) -> None:
    created_at = str(payload.get("created_at") or utc_now())
    encoded = json.dumps(payload, default=str, separators=(",", ":"))
    with _connect() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO ledger_objects
            (object_id, object_type, case_id, parent_id, topic, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (object_id, object_type, case_id, parent_id, topic, encoded, created_at),
        )
        if object_type == "risk_authorization":
            db.execute(
                """
                INSERT OR IGNORE INTO risk_authorization_state
                (authorization_id, consumed, consumed_at)
                VALUES (?, 0, NULL)
                """,
                (object_id,),
            )

        if object_type == "paper_authorization":
            db.execute(
                """
                INSERT OR IGNORE INTO paper_authorization_state
                (authorization_id, consumed, consumed_at)
                VALUES (?, 0, NULL)
                """,
                (object_id,),
            )


def record_event(
    case_id: str,
    event_type: str,
    *,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": f"event_{uuid4().hex}",
        "case_id": case_id,
        "event_type": event_type,
        "entity_id": entity_id,
        "payload": payload or {},
        "created_at": utc_now(),
    }
    with _connect() as db:
        db.execute(
            """
            INSERT INTO audit_events
            (event_id, case_id, event_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                case_id,
                event_type,
                entity_id,
                json.dumps(event["payload"], default=str, separators=(",", ":")),
                event["created_at"],
            ),
        )
    return event


def get_object(object_id: str) -> dict[str, Any] | None:
    with _connect() as db:
        row = db.execute(
            "SELECT payload_json FROM ledger_objects WHERE object_id = ?",
            (object_id,),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None


def latest_object(
    object_type: str,
    *,
    topic: str | None = None,
    case_id: str | None = None,
) -> dict[str, Any] | None:
    clauses = ["object_type = ?"]
    params: list[Any] = [object_type]
    if topic is not None:
        clauses.append("topic = ?")
        params.append(topic)
    if case_id is not None:
        clauses.append("case_id = ?")
        params.append(case_id)
    query = (
        "SELECT payload_json FROM ledger_objects WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_at DESC LIMIT 1"
    )
    with _connect() as db:
        row = db.execute(query, params).fetchone()
    return json.loads(row["payload_json"]) if row else None


def list_objects(case_id: str, object_type: str | None = None) -> list[dict[str, Any]]:
    if object_type:
        query = (
            "SELECT payload_json FROM ledger_objects "
            "WHERE case_id = ? AND object_type = ? ORDER BY created_at ASC"
        )
        params = (case_id, object_type)
    else:
        query = (
            "SELECT payload_json FROM ledger_objects "
            "WHERE case_id = ? ORDER BY created_at ASC"
        )
        params = (case_id,)
    with _connect() as db:
        rows = db.execute(query, params).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def consume_authorization(authorization_id: str) -> bool:
    """Atomically consume a risk authorization. Returns False if missing/already used."""
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT consumed FROM risk_authorization_state WHERE authorization_id = ?",
            (authorization_id,),
        ).fetchone()
        if not row or row["consumed"]:
            db.rollback()
            return False
        db.execute(
            """
            UPDATE risk_authorization_state
            SET consumed = 1, consumed_at = ?
            WHERE authorization_id = ? AND consumed = 0
            """,
            (utc_now(), authorization_id),
        )
        db.commit()
        return True


def consume_paper_authorization(
    authorization_id: str,
) -> bool:
    """
    Atomically consume a governed paper authorization.

    Separate from legacy risk_authorization consumption.
    Paper Execution does not use this token yet.
    """
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")

        row = db.execute(
            """
            SELECT consumed
            FROM paper_authorization_state
            WHERE authorization_id = ?
            """,
            (authorization_id,),
        ).fetchone()

        if not row or row["consumed"]:
            db.rollback()
            return False

        db.execute(
            """
            UPDATE paper_authorization_state
            SET consumed = 1,
                consumed_at = ?
            WHERE authorization_id = ?
              AND consumed = 0
            """,
            (
                utc_now(),
                authorization_id,
            ),
        )

        db.commit()
        return True


def paper_authorization_consumed(
    authorization_id: str,
) -> bool | None:
    with _connect() as db:
        row = db.execute(
            """
            SELECT consumed
            FROM paper_authorization_state
            WHERE authorization_id = ?
            """,
            (authorization_id,),
        ).fetchone()

    if not row:
        return None

    return bool(row["consumed"])


def authorization_consumed(authorization_id: str) -> bool | None:
    with _connect() as db:
        row = db.execute(
            "SELECT consumed FROM risk_authorization_state WHERE authorization_id = ?",
            (authorization_id,),
        ).fetchone()
    if not row:
        return None
    return bool(row["consumed"])


def get_audit(case_id: str) -> dict[str, Any]:
    with _connect() as db:
        object_rows = db.execute(
            """
            SELECT object_id, object_type, parent_id, payload_json, created_at
            FROM ledger_objects
            WHERE case_id = ?
            ORDER BY created_at ASC
            """,
            (case_id,),
        ).fetchall()
        event_rows = db.execute(
            """
            SELECT event_id, event_type, entity_id, payload_json, created_at
            FROM audit_events
            WHERE case_id = ?
            ORDER BY created_at ASC
            """,
            (case_id,),
        ).fetchall()

    objects = [
        {
            "object_id": row["object_id"],
            "object_type": row["object_type"],
            "parent_id": row["parent_id"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in object_rows
    ]
    events = [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "entity_id": row["entity_id"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in event_rows
    ]
    return {"case_id": case_id, "objects": objects, "events": events}


init_ledger()
