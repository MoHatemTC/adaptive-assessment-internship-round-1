"""Tests for Hugging Face ArcFace face verification."""

from __future__ import annotations

import numpy as np
import pytest

from app.proctoring.hf_face import (
    HuggingFaceArcFaceMatchProvider,
    cosine_similarity,
    preprocess_face_image,
)
from app.proctoring.identity import get_face_match_provider
from app.proctoring.settings import ProctoringSettings


def test_cosine_similarity_identical_vectors():
    vector = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    left = np.array([1.0, 0.0], dtype=np.float32)
    right = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(left, right) == pytest.approx(0.0)


def test_preprocess_face_image_shape():
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buffer, format="PNG")
    batch = preprocess_face_image(buffer.getvalue())
    assert batch.shape == (1, 112, 112, 3)


def test_get_face_match_provider_prefers_huggingface_in_auto_mode(monkeypatch):
    settings = ProctoringSettings(
        FACE_PROVIDER="auto",
        HF_FACE_MODEL_REPO="onnx-community/arcface-onnx",
        HF_FACE_MODEL_FILE="arcface.onnx",
    )
    monkeypatch.setattr(
        "app.proctoring.identity.get_proctoring_settings",
        lambda: settings,
    )

    provider = get_face_match_provider()
    assert provider.__class__.__name__ == "HuggingFaceArcFaceMatchProvider"


@pytest.mark.asyncio
async def test_hf_provider_compare_uses_embeddings(monkeypatch):
    settings = ProctoringSettings(
        FACE_PROVIDER="huggingface",
        FACE_MATCH_THRESHOLD=0.7,
    )
    provider = HuggingFaceArcFaceMatchProvider(settings)

    same = np.ones(512, dtype=np.float32)
    different = np.zeros(512, dtype=np.float32)
    different[0] = 1.0

    async def _fake_embed(image_bytes: bytes, settings=None) -> np.ndarray:
        return same if image_bytes == b"ref" else different

    monkeypatch.setattr(
        "app.proctoring.hf_face.embed_image_bytes",
        _fake_embed,
    )

    fail_result = await provider.compare("cmVm", "ZGlmZg==")
    assert fail_result.matched is False
    assert fail_result.score < 0.7

    async def _fake_embed_match(image_bytes: bytes, settings=None) -> np.ndarray:
        return same

    monkeypatch.setattr(
        "app.proctoring.hf_face.embed_image_bytes",
        _fake_embed_match,
    )

    pass_result = await provider.compare("cmVm", "cmVm")
    assert pass_result.matched is True
    assert pass_result.score == pytest.approx(1.0)
