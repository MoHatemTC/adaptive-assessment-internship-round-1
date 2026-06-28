"""Database normalization audit helpers (WP-3).

Inventory memory-related tables, verify the diagram schema fork is resolved,
and report orphan rows before adding FK constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

# Platform memory store plus per-tool extension tables (not redundant duplicates).
MEMORY_TABLES = ("memory_cards", "code_memory_cards", "voice_memory_cards")

# Legacy diagram table dropped by 0013_diagram_svg_rebuild.
LEGACY_DIAGRAM_TABLES = ("diagram_answers",)

CANONICAL_DIAGRAM_TABLES = ("diagram_questions", "diagram_responses")

DIAGRAM_QUESTION_COLUMNS = frozenset(
    {
        "id",
        "svg_content",
        "prompt",
        "correct_label",
        "rubric",
        "difficulty",
        "dimension",
        "created_at",
    }
)


@dataclass
class TableInventory:
    """Row counts and column names for one public table."""

    name: str
    exists: bool
    row_count: int = 0
    columns: list[str] = field(default_factory=list)


@dataclass
class NormalizationAuditReport:
    """Structured output from :func:`run_normalization_audit`."""

    tables: dict[str, TableInventory]
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _table_names(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _inventory_table(conn: Connection, table: str) -> TableInventory:
    names = _table_names(conn)
    if table not in names:
        return TableInventory(name=table, exists=False)
    columns = [c["name"] for c in inspect(conn).get_columns(table)]
    count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
    return TableInventory(
        name=table,
        exists=True,
        row_count=int(count),
        columns=columns,
    )


def _orphan_count(
    conn: Connection,
    *,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str = "id",
) -> int:
    sql = text(
        f"""
        SELECT COUNT(*)
        FROM "{child_table}" c
        LEFT JOIN "{parent_table}" p ON c.{child_column} = p.{parent_column}
        WHERE c.{child_column} IS NOT NULL AND p.{parent_column} IS NULL
        """
    )
    return int(conn.execute(sql).scalar_one())


def run_normalization_audit(conn: Connection) -> NormalizationAuditReport:
    """Audit memory tables and diagram schema against WP-3 expectations."""
    report = NormalizationAuditReport(tables={})

    for name in (*MEMORY_TABLES, *LEGACY_DIAGRAM_TABLES, *CANONICAL_DIAGRAM_TABLES):
        report.tables[name] = _inventory_table(conn, name)

    # Diagram fork: legacy table must be gone; canonical tables must exist.
    legacy = report.tables.get("diagram_answers")
    if legacy and legacy.exists:
        report.issues.append(
            "diagram_answers still exists — run alembic upgrade head (0013_diagram_svg_rebuild)"
        )

    for required in CANONICAL_DIAGRAM_TABLES:
        inv = report.tables.get(required)
        if inv is None or not inv.exists:
            report.issues.append(f"missing required table: {required}")

    questions = report.tables.get("diagram_questions")
    if questions and questions.exists:
        missing_cols = DIAGRAM_QUESTION_COLUMNS - set(questions.columns)
        if missing_cols:
            report.issues.append(
                f"diagram_questions missing columns: {sorted(missing_cols)}"
            )

    # Memory extension tables hold tool-specific fields; platform memory_cards is canonical.
    code_detail = report.tables.get("code_memory_cards")
    voice_detail = report.tables.get("voice_memory_cards")
    platform = report.tables.get("memory_cards")
    if platform and platform.exists:
        report.notes.append(
            f"memory_cards rows={platform.row_count} (platform canonical store)"
        )
    if code_detail and code_detail.exists:
        report.notes.append(
            f"code_memory_cards rows={code_detail.row_count} "
            "(extension table — sandbox scores, test_results; not a duplicate of memory_cards)"
        )
    if voice_detail and voice_detail.exists:
        report.notes.append(
            f"voice_memory_cards rows={voice_detail.row_count} "
            "(extension table — rubric/communication JSON; not a duplicate of memory_cards)"
        )

    if code_detail and code_detail.exists and platform and platform.exists:
        orphans = _orphan_count(
            conn,
            child_table="code_memory_cards",
            child_column="memory_card_id",
            parent_table="memory_cards",
        )
        if orphans:
            report.issues.append(
                f"code_memory_cards has {orphans} orphan memory_card_id row(s)"
            )

    if voice_detail and voice_detail.exists and platform and platform.exists:
        orphans = _orphan_count(
            conn,
            child_table="voice_memory_cards",
            child_column="memory_card_id",
            parent_table="memory_cards",
        )
        if orphans:
            report.issues.append(
                f"voice_memory_cards has {orphans} orphan memory_card_id row(s)"
            )

    return report


def format_report(report: NormalizationAuditReport) -> str:
    """Human-readable audit summary for CLI or CI logs."""
    lines: list[str] = ["=== WP-3 database normalization audit ==="]
    for name, inv in sorted(report.tables.items()):
        if not inv.exists:
            lines.append(f"  {name}: (absent)")
            continue
        lines.append(f"  {name}: {inv.row_count} rows, columns={inv.columns}")
    for note in report.notes:
        lines.append(f"NOTE: {note}")
    for issue in report.issues:
        lines.append(f"ISSUE: {issue}")
    lines.append("RESULT: OK" if report.ok else "RESULT: FAILED")
    return "\n".join(lines)
