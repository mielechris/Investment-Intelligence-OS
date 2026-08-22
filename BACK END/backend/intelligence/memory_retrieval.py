import json
import os
import re
import sqlite3
from pathlib import Path


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "was", "were",
    "will", "with", "without", "new", "current", "paper", "market", "evidence", "company", "filing",
}


def _database_path() -> Path:
    configured = os.getenv("IIOS_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "iios.db"


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9._-]{1,}", value.lower())
    return {word for word in words if word not in _STOPWORDS and len(word) > 2}


def _is_synthetic_context(event: dict) -> bool:
    text = " ".join(
        str(event.get(key) or "")
        for key in ("source_name", "title", "summary", "url")
    ).lower()
    return "synthetic" in text or "iios-test" in text or "test fixture" in text


def retrieve_relevant_patterns(event: dict, *, limit: int = 3) -> list[dict]:
    """Return compact prior lessons ranked by lexical overlap with the incoming event.

    Synthetic lessons are excluded from real-market contexts so workflow tests can never
    become investment evidence. This intentionally uses transparent lexical scoring as the
    V1 implementation; the interface can later be backed by embeddings/vector search.
    """
    limit = max(1, min(limit, 10))
    query_text = " ".join(
        str(event.get(key) or "")
        for key in ("source_name", "source_kind", "title", "summary", "url")
    )
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []

    database_path = _database_path()
    if not database_path.exists():
        return []

    try:
        connection = sqlite3.connect(database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM history_pattern_library ORDER BY created_at DESC LIMIT 250"
        ).fetchall()
        connection.close()
    except sqlite3.Error:
        return []

    allow_synthetic = _is_synthetic_context(event)
    scored: list[tuple[float, dict]] = []
    for row in rows:
        item = dict(row)
        synthetic = bool(item.get("synthetic_fixture"))
        if synthetic and not allow_synthetic:
            continue

        try:
            tags = json.loads(item.get("tags_payload") or "[]")
        except (json.JSONDecodeError, TypeError):
            tags = []
        try:
            lesson = json.loads(item.get("lesson_payload") or "{}")
        except (json.JSONDecodeError, TypeError):
            lesson = {}

        searchable = " ".join(
            [
                str(item.get("symbol") or ""),
                str(item.get("outcome") or ""),
                str(item.get("headline") or ""),
                " ".join(str(tag) for tag in tags),
                json.dumps(lesson, sort_keys=True),
            ]
        )
        pattern_tokens = _tokens(searchable)
        overlap = query_tokens.intersection(pattern_tokens)
        if not overlap:
            continue

        # Transparent scoring: reward unique token overlap and exact symbol/title fragments.
        score = float(len(overlap))
        symbol = str(item.get("symbol") or "").lower()
        if symbol and symbol in query_text.lower():
            score += 3.0
        headline = str(item.get("headline") or "").lower()
        for token in query_tokens:
            if token in headline:
                score += 0.25

        scored.append(
            (
                score,
                {
                    "pattern_id": item.get("pattern_id"),
                    "symbol": item.get("symbol"),
                    "outcome": item.get("outcome"),
                    "return_pct": item.get("return_pct"),
                    "headline": item.get("headline"),
                    "tags": tags,
                    "lesson": lesson,
                    "synthetic_fixture": synthetic,
                    "relevance_score": round(score, 2),
                    "matched_terms": sorted(overlap)[:12],
                },
            )
        )

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]
