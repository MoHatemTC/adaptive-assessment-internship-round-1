"""Admin API tests for judge review workflow."""

from __future__ import annotations

import json
import uuid

import pytest

from app.agent.nodes.judge import SessionJudgeResult, judge_result_to_json
from app.core.database import async_session, get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.sessions.models import AssessmentSession


@pytest.fixture
async def admin_db_client(client):
    async def _override_get_db():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield client
    fastapi_app.dependency_overrides.pop(get_db, None)


def _admin_headers() -> dict[str, str]:
    token = create_access_token({"sub": "admin", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_pending_judge_reviews(admin_db_client, monkeypatch):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    async with async_session() as db:
        db.add(
            AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"name": "Karim"}),
                status="pending_review",
                judge_review_json=judge_result_to_json(
                    SessionJudgeResult(
                        session_id=session_id,
                        llm_judge_score=0.4,
                        narrative="Needs review",
                        grade_result_count=1,
                        review_status="pending_admin_review",
                        review_reason="inconsistent rubric",
                    )
                ),
            )
        )
        await db.commit()

    response = await admin_db_client.get(
        "/api/v1/admin/sessions/pending-review",
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert any(row["session_id"] == session_id for row in body)


@pytest.mark.asyncio
async def test_approve_judge_review(admin_db_client, monkeypatch):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    async with async_session() as db:
        db.add(
            AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"name": "Karim", "email": "k@example.com"}),
                status="pending_review",
                judge_review_json=judge_result_to_json(
                    SessionJudgeResult(
                        session_id=session_id,
                        llm_judge_score=0.75,
                        narrative="Approve me",
                        grade_result_count=1,
                        review_status="pending_admin_review",
                        review_reason="check",
                    )
                ),
            )
        )
        await db.commit()

    scheduled: list[str] = []
    monkeypatch.setattr(
        "app.workers.email_tasks.schedule_finalize_after_judge_approval",
        lambda sid, learner_email=None: scheduled.append(sid),
    )

    response = await admin_db_client.post(
        f"/api/v1/admin/sessions/{session_id}/judge-review/approve",
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["review_status"] == "confirmed"
    assert scheduled == [session_id]
