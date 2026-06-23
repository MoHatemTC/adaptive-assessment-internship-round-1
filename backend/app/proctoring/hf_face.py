"""Hugging Face ArcFace embeddings for server-side face verification."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

import numpy as np
from huggingface_hub import hf_hub_download
from PIL import Image

from app.core.logging import get_logger
from app.proctoring.identity import (
    FaceMatchResult,
    IdentityUnavailableError,
    _decode_image,
)
from app.proctoring.settings import ProctoringSettings, get_proctoring_settings

if TYPE_CHECKING:
    import onnxruntime as ort

_logger = get_logger(__name__)

_INPUT_SIZE = 112
_SESSION: ort.InferenceSession | None = None
_SESSION_LOCK = asyncio.Lock()


def preprocess_face_image(image_bytes: bytes) -> np.ndarray:
    """Resize an RGB face crop to ArcFace input tensor (1, 112, 112, 3)."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = image.resize((_INPUT_SIZE, _INPUT_SIZE), Image.Resampling.BILINEAR)
    pixels = np.asarray(image, dtype=np.float32)
    pixels = (pixels - 127.5) / 128.0
    return pixels[np.newaxis, ...]


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Return cosine similarity between two embedding vectors."""
    left_norm = left / np.linalg.norm(left)
    right_norm = right / np.linalg.norm(right)
    return float(np.dot(left_norm, right_norm))


def _download_model(settings: ProctoringSettings) -> str:
    token = settings.HF_TOKEN.get_secret_value().strip() or None
    return hf_hub_download(
        repo_id=settings.HF_FACE_MODEL_REPO,
        filename=settings.HF_FACE_MODEL_FILE,
        token=token,
    )


def _create_session(model_path: str) -> ort.InferenceSession:
    import onnxruntime as ort

    return ort.InferenceSession(
        model_path,
        providers=["CPUExecutionProvider"],
    )


async def _get_session(settings: ProctoringSettings) -> ort.InferenceSession:
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    async with _SESSION_LOCK:
        if _SESSION is not None:
            return _SESSION

        model_path = await asyncio.to_thread(_download_model, settings)
        _SESSION = await asyncio.to_thread(_create_session, model_path)
        _logger.info(
            "hf_arcface_model_loaded",
            repo=settings.HF_FACE_MODEL_REPO,
            file=settings.HF_FACE_MODEL_FILE,
        )
        return _SESSION


def _run_embedding(session: ort.InferenceSession, batch: np.ndarray) -> np.ndarray:
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    embedding = session.run([output_name], {input_name: batch})[0]
    return embedding[0]


async def embed_image_bytes(
    image_bytes: bytes,
    settings: ProctoringSettings | None = None,
) -> np.ndarray:
    """Return a face embedding for raw image bytes."""
    resolved = settings or get_proctoring_settings()
    session = await _get_session(resolved)
    batch = preprocess_face_image(image_bytes)
    return await asyncio.to_thread(_run_embedding, session, batch)


class HuggingFaceArcFaceMatchProvider:
    """Compare faces via ArcFace embeddings from a Hugging Face ONNX model."""

    def __init__(self, settings: ProctoringSettings | None = None) -> None:
        self._settings = settings or get_proctoring_settings()

    async def compare(self, reference_b64: str, live_b64: str) -> FaceMatchResult:
        if not self._settings.hf_face_configured:
            raise IdentityUnavailableError(
                "Hugging Face face verification is not configured "
                "(set FACE_PROVIDER=huggingface and HF_TOKEN if needed)"
            )

        try:
            reference_bytes = _decode_image(reference_b64)
            live_bytes = _decode_image(live_b64)
            ref_embedding = await embed_image_bytes(reference_bytes, self._settings)
            live_embedding = await embed_image_bytes(live_bytes, self._settings)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - surface provider failures cleanly
            _logger.warning("hf_face_embedding_failed", error=str(exc))
            raise IdentityUnavailableError("Hugging Face face embedding failed") from exc

        score = cosine_similarity(ref_embedding, live_embedding)
        matched = score >= self._settings.FACE_MATCH_THRESHOLD
        return FaceMatchResult(score=score, matched=matched)
