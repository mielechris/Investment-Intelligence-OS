import json
import sqlite3

from intelligence.memory_retrieval import retrieve_relevant_patterns


def _seed_pattern(db_path, *, pattern_id, symbol, headline, tags, lesson, synthetic=False):
    connection = sqlite3.connect(db_path)
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
        INSERT INTO history_pattern_library
        (pattern_id, review_id, symbol, outcome, return_pct, headline, tags_payload,
         lesson_payload, synthetic_fixture, created_at)
        VALUES (?, ?, ?, 'WIN', 5.0, ?, ?, ?, ?, '2026-08-21T00:00:00+00:00')
        """,
        (
            pattern_id,
            f"review-{pattern_id}",
            symbol,
            headline,
            json.dumps(tags),
            json.dumps(lesson),
            int(synthetic),
        ),
    )
    connection.commit()
    connection.close()


def test_synthetic_memory_is_excluded_from_real_market_context(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _seed_pattern(
        db_path,
        pattern_id="synthetic-1",
        symbol="IIOS-TEST",
        headline="Synthetic IPO liquidity workflow validation",
        tags=["IPO", "LIQUIDITY", "SYNTHETIC_FIXTURE"],
        lesson={"reusable_patterns": ["Synthetic IPO liquidity process test"]},
        synthetic=True,
    )
    monkeypatch.setenv("IIOS_DB_PATH", str(db_path))

    event = {
        "source_name": "SEC EDGAR",
        "source_kind": "company",
        "title": "F-1 Example Operating Company",
        "summary": "IPO liquidity and listing evidence",
    }
    assert retrieve_relevant_patterns(event) == []


def test_synthetic_memory_is_available_to_synthetic_context(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _seed_pattern(
        db_path,
        pattern_id="synthetic-1",
        symbol="IIOS-TEST",
        headline="Synthetic IPO liquidity workflow validation",
        tags=["IPO", "LIQUIDITY", "SYNTHETIC_FIXTURE"],
        lesson={"reusable_patterns": ["Synthetic IPO liquidity process test"]},
        synthetic=True,
    )
    monkeypatch.setenv("IIOS_DB_PATH", str(db_path))

    event = {
        "source_name": "IIOS synthetic test fixture",
        "source_kind": "market",
        "title": "IIOS-TEST IPO liquidity test",
        "summary": "Synthetic fixture validates IPO liquidity workflow",
    }
    results = retrieve_relevant_patterns(event)
    assert len(results) == 1
    assert results[0]["pattern_id"] == "synthetic-1"
    assert results[0]["synthetic_fixture"] is True


def test_retrieval_ranks_higher_overlap_first(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    _seed_pattern(
        db_path,
        pattern_id="ipo-strong",
        symbol="ABCD",
        headline="IPO dilution liquidity governance risk",
        tags=["IPO", "DILUTION", "LIQUIDITY", "GOVERNANCE"],
        lesson={"reusable_patterns": ["Require confirmed listing liquidity and dilution terms"]},
    )
    _seed_pattern(
        db_path,
        pattern_id="macro-weak",
        symbol="SPY",
        headline="Rates regime lesson",
        tags=["RATES", "MACRO"],
        lesson={"reusable_patterns": ["Watch policy expectations"]},
    )
    monkeypatch.setenv("IIOS_DB_PATH", str(db_path))

    event = {
        "source_name": "SEC EDGAR",
        "source_kind": "company",
        "title": "ABCD F-1 IPO",
        "summary": "IPO dilution, governance, listing liquidity and share structure",
    }
    results = retrieve_relevant_patterns(event, limit=2)
    assert results
    assert results[0]["pattern_id"] == "ipo-strong"
    assert results[0]["relevance_score"] > 0
