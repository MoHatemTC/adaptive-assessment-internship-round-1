#!/usr/bin/env python3
"""Create or update the team demo assessment (active, all tools enabled).

Usage:
    docker compose exec backend python scripts/seed_demo_assessment.py

Then set NEXT_PUBLIC_DEMO_ASSESSMENT_ID in .env to the printed id.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import select

from app.admin.models import Assessment
from app.core.database import async_session

# Stable id so teams can commit a known demo UUID in .env.example
DEMO_ASSESSMENT_ID = "a1b2c3d4-e5f6-4789-a012-3456789abcde"

DEMO_BLUEPRINT = {
    "tools": ["coding", "mcq", "voice", "diagram"],
    "proctoring": {
        "high_severity_threshold": 3,
        "camera_poll_interval_seconds": 1.5,
        "event_cooldown_seconds": 30,
        "require_camera": True,
        "require_microphone": False,
        "enabled_checks": [
            "tab_switch",
            "paste",
            "copy",
            "face_absent",
            "multiple_persons_detected",
            "candidate_absent",
            "session_started",
            "session_stopped",
        ],
    },
}

DEMO_TOOL_CONFIG = {
    "coding": True,
    "mcq": True,
    "voice": True,
    "diagram": True,
    "proctoring": DEMO_BLUEPRINT["proctoring"],
}


async def main() -> None:
    async with async_session() as db:
        result = await db.exec(
            select(Assessment).where(Assessment.id == DEMO_ASSESSMENT_ID)
        )
        row = result.first()
        if row is None:
            row = Assessment(
                id=DEMO_ASSESSMENT_ID,
                title="Masaar Platform Demo",
                prompt="Adaptive multi-tool assessment demo for Sprint 3.",
                blueprint_json=json.dumps(DEMO_BLUEPRINT),
                tool_config=json.dumps(DEMO_TOOL_CONFIG),
                status="active",
            )
            db.add(row)
            action = "created"
        else:
            row.title = "Masaar Platform Demo"
            row.prompt = "Adaptive multi-tool assessment demo for Sprint 3."
            row.blueprint_json = json.dumps(DEMO_BLUEPRINT)
            row.tool_config = json.dumps(DEMO_TOOL_CONFIG)
            row.status = "active"
            db.add(row)
            action = "updated"

        await db.commit()
        await db.refresh(row)

    print("=== Demo assessment", action, "===")
    print(f"assessment_id: {row.id}")
    print(f"learner_verify_url: /assessment/{row.id}/verify")
    print("")
    print("Add to .env:")
    print(f"NEXT_PUBLIC_DEMO_ASSESSMENT_ID={row.id}")


if __name__ == "__main__":
    asyncio.run(main())
