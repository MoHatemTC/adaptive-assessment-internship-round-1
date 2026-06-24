"""API tests for admin authentication and assessment CRUD."""

from __future__ import annotations

import json
import uuid

import pytest

from app.admin.models import Assessment
from app.core.database import async_session, get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app


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
async def test_admin_login_returns_token(admin_db_client):
    response = await admin_db_client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


@pytest.mark.asyncio
async def test_admin_login_rejects_bad_credentials(admin_db_client):
    response = await admin_db_client.post(
        "/api/v1/auth/token",
        data={"username": "admin", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_assessments_requires_admin(admin_db_client):
    response = await admin_db_client.get("/api/v1/admin/assessments")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_and_get_assessment(admin_db_client):
    create_resp = await admin_db_client.post(
        "/api/v1/admin/assessments",
        headers=_admin_headers(),
        json={
            "title": "Platform Smoke",
            "prompt": "Complete the assessment.",
            "blueprint_json": {"voice": {"max_questions": 3}},
            "tool_config": {"proctoring": {"enabled_checks": ["tab_switch"]}},
            "status": "active",
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["title"] == "Platform Smoke"
    assert created["blueprint_json"]["voice"]["max_questions"] == 3

    list_resp = await admin_db_client.get(
        "/api/v1/admin/assessments",
        headers=_admin_headers(),
    )
    assert list_resp.status_code == 200
    assert any(row["id"] == created["id"] for row in list_resp.json())

    get_resp = await admin_db_client.get(
        f"/api/v1/admin/assessments/{created['id']}",
        headers=_admin_headers(),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["tool_config"]["proctoring"]["enabled_checks"] == ["tab_switch"]


@pytest.mark.asyncio
async def test_update_assessment(admin_db_client):
    assessment_id = str(uuid.uuid4())
    async with async_session() as db:
        db.add(
            Assessment(
                id=assessment_id,
                title="Old",
                prompt="x",
                blueprint_json=json.dumps({}),
                tool_config=json.dumps({}),
                status="draft",
            )
        )
        await db.commit()

    response = await admin_db_client.patch(
        f"/api/v1/admin/assessments/{assessment_id}",
        headers=_admin_headers(),
        json={"title": "Updated", "status": "active"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated"
    assert body["status"] == "active"


@pytest.mark.asyncio
async def test_get_assessment_not_found(admin_db_client):
    response = await admin_db_client.get(
        f"/api/v1/admin/assessments/{uuid.uuid4()}",
        headers=_admin_headers(),
    )
    assert response.status_code == 404
