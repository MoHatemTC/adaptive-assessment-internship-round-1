#!/usr/bin/env python3
"""CLI: audit Supabase/Postgres schema for WP-3 normalization."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.database import engine
from app.db.audit_normalization import format_report, run_normalization_audit


async def main() -> int:
    async with engine.connect() as conn:
        # SQLAlchemy 2 async connections need sync access for inspect().
        report = await conn.run_sync(run_normalization_audit)
        print(format_report(report))
        if report.ok:
            counts = await conn.execute(
                text(
                    """
                    SELECT 'memory_cards' AS t, COUNT(*) FROM memory_cards
                    UNION ALL
                    SELECT 'code_memory_cards', COUNT(*) FROM code_memory_cards
                    UNION ALL
                    SELECT 'voice_memory_cards', COUNT(*) FROM voice_memory_cards
                    """
                )
            )
            print("\n=== Row-count snapshot (verification) ===")
            for row in counts:
                print(f"  {row[0]}: {row[1]}")
        return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
