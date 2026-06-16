"""
test_diagram.py
Three groups:
  1. Image validation  — bad MIME, oversized, valid JPEG
  2. API round-trip    — GET shape/404, POST persists + returns grading
  3. Vision format     — image arrives as content block, not text
"""

import base64
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.features.diagram.models import Difficulty, DiagramAnswer, DiagramQuestion, SkillDimension
from app.features.diagram.service import (
    MAX_IMAGE_BYTES,
    _build_vision_message,
    _fetch_and_validate_image,
)

client = TestClient(app)

Q_ID = uuid.uuid4()
S_ID = uuid.uuid4()


def _fake_question():
    return DiagramQuestion(
        id=Q_ID,
        image_url="https://cdn.example.com/q1.jpg",
        prompt="Label the network diagram.",
        rubric="1 point per correct label.",
        difficulty=Difficulty.medium,
        dimension=SkillDimension.digital_ai,
    )


def _fake_answer():
    return DiagramAnswer(
        id=uuid.uuid4(),
        session_id=S_ID,
        question_id=Q_ID,
        answer_text="Router in centre, three switches.",
        score=0.8,
        grading_feedback="Correct router; missed one switch.",
        graded_at=datetime.datetime.utcnow(),
    )


def _mock_http(content_type: str, content: bytes):
    r = MagicMock()
    r.headers = {"content-type": content_type}
    r.content = content
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.asyncio
async def test_rejects_bad_mime():
    with patch("httpx.AsyncClient.get", return_value=_mock_http("application/pdf", b"%PDF")):
        with pytest.raises(ValueError, match="Unsupported image type"):
            await _fetch_and_validate_image("https://example.com/file.pdf")


@pytest.mark.asyncio
async def test_rejects_oversized():
    big = b"\x00" * (MAX_IMAGE_BYTES + 1)
    with patch("httpx.AsyncClient.get", return_value=_mock_http("image/jpeg", big)):
        with pytest.raises(ValueError, match="Image too large"):
            await _fetch_and_validate_image("https://example.com/big.jpg")


@pytest.mark.asyncio
async def test_accepts_valid_jpeg():
    data = b"\xff\xd8\xff" + b"\x00" * 100
    with patch("httpx.AsyncClient.get", return_value=_mock_http("image/jpeg", data)):
        b64, mime = await _fetch_and_validate_image("https://example.com/ok.jpg")
    assert mime == "image/jpeg"
    assert base64.b64decode(b64) == data


def test_get_question_shape():
    with patch("app.features.diagram.service.DiagramService.fetch_question",
               new_callable=AsyncMock, return_value=_fake_question()):
        r = client.get(f"/diagram/{Q_ID}")
    assert r.status_code == 200
    data = r.json()
    assert "image_url" in data and "prompt" in data
    assert "rubric" not in data


def test_get_question_404():
    with patch("app.features.diagram.service.DiagramService.fetch_question",
               new_callable=AsyncMock, return_value=None):
        r = client.get(f"/diagram/{uuid.uuid4()}")
    assert r.status_code == 404


def test_submit_answer_returns_grading():
    with (
        patch("app.features.diagram.service.DiagramService.submit_answer",
              new_callable=AsyncMock, return_value=_fake_answer()),
        patch("app.features.diagram.service.DiagramService.fetch_question",
              new_callable=AsyncMock, return_value=_fake_question()),
    ):
        r = client.post(f"/diagram/{Q_ID}/answer", json={
            "session_id": str(S_ID),
            "answer_text": "Router in centre, three switches.",
        })
    assert r.status_code == 201
    data = r.json()
    assert 0.0 <= data["score"] <= 1.0
    assert "dimension" in data
    assert "grading_feedback" in data


def test_vision_message_has_image_content_block():
    b64 = base64.b64encode(b"fake").decode()
    msgs = _build_vision_message("Describe.", "Rubric.", b64, "image/jpeg")
    types = [b["type"] for b in msgs[0]["content"]]
    assert "image_url" in types, "Image must be a vision content block, not text"


def test_vision_image_is_data_uri():
    b64 = base64.b64encode(b"fake").decode()
    msgs = _build_vision_message("Describe.", "Rubric.", b64, "image/png")
    img_block = next(b for b in msgs[0]["content"] if b["type"] == "image_url")
    assert img_block["image_url"]["url"].startswith("data:image/png;base64,")