"""Tests for WP-3 database normalization audit."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from app.db.audit_normalization import run_normalization_audit


@pytest.fixture
def sqlite_conn():
    engine = create_engine("sqlite:///:memory:")
    statements = [
        """
        CREATE TABLE memory_cards (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            difficulty TEXT NOT NULL,
            evidence_summary TEXT NOT NULL,
            dimension_signals TEXT NOT NULL,
            passed INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE code_memory_cards (
            id INTEGER PRIMARY KEY,
            memory_card_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            submission_id INTEGER NOT NULL,
            sandbox_score REAL NOT NULL,
            overall_rubric_score REAL NOT NULL,
            test_results TEXT NOT NULL,
            approach_feedback TEXT NOT NULL,
            efficiency_feedback TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE diagram_questions (
            id INTEGER PRIMARY KEY,
            svg_content TEXT NOT NULL,
            prompt TEXT NOT NULL,
            correct_label TEXT NOT NULL,
            rubric TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            dimension TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE diagram_responses (
            id INTEGER PRIMARY KEY,
            question_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            answer_text TEXT NOT NULL,
            score REAL
        )
        """,
        """
        INSERT INTO memory_cards VALUES (
            1, 'sess-1', 'code', 0, 'easy', 'summary', '{}', 1
        )
        """,
        """
        INSERT INTO code_memory_cards VALUES (
            1, 1, 'sess-1', 0, 10, 0.8, 0.9, '[]', 'ok', 'ok'
        )
        """,
    ]
    with engine.connect() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()
        yield conn


def test_audit_passes_canonical_schema(sqlite_conn):
    report = run_normalization_audit(sqlite_conn)
    assert report.ok
    assert "diagram_answers" in report.tables
    assert report.tables["diagram_answers"].exists is False
    assert report.tables["diagram_responses"].exists is True


def test_audit_flags_legacy_diagram_answers(sqlite_conn):
    sqlite_conn.execute(
        text(
            """
            CREATE TABLE diagram_answers (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                answer_text TEXT NOT NULL
            )
            """
        )
    )
    sqlite_conn.commit()
    report = run_normalization_audit(sqlite_conn)
    assert not report.ok
    assert any("diagram_answers still exists" in i for i in report.issues)


def test_audit_flags_orphan_code_memory_cards(sqlite_conn):
    sqlite_conn.execute(
        text(
            """
            INSERT INTO code_memory_cards VALUES (
                2, 999, 'sess-2', 1, 11, 0.5, 0.5, '[]', 'x', 'x'
            )
            """
        )
    )
    sqlite_conn.commit()
    report = run_normalization_audit(sqlite_conn)
    assert not report.ok
    assert any("orphan memory_card_id" in i for i in report.issues)


def test_audit_notes_extension_tables_are_not_duplicates(sqlite_conn):
    report = run_normalization_audit(sqlite_conn)
    assert any("extension table" in n for n in report.notes)
