"""Server-side face-match identity verification."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.logging import get_logger
from app.proctoring.settings import ProctoringSettings, get_proctoring_settings

_logger = get_logger(__name__)


class IdentityUnavailableError(Exception):
    """Raised when face-match credentials are missing or the provider fails."""


@dataclass(frozen=True)
class FaceMatchResult:
    """Outcome of comparing a reference photo to a live capture."""

    score: float
    matched: bool


class FaceMatchProvider(Protocol):
    """Pluggable face comparison — swap for mocks in tests."""

    async def compare(self, reference_b64: str, live_b64: str) -> FaceMatchResult:
        """Compare two base64-encoded images and return match confidence."""
        ...


def _decode_image(b64_value: str) -> bytes:
    """Decode a base64 image string, tolerating a data-URL prefix."""
    payload = b64_value.strip()
    if "," in payload and payload.startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64 image payload") from exc


class AzureFaceMatchProvider:
    """Azure Cognitive Services Face API — detect then verify."""

    def __init__(self, settings: ProctoringSettings | None = None) -> None:
        self._settings = settings or get_proctoring_settings()

    async def compare(self, reference_b64: str, live_b64: str) -> FaceMatchResult:
        if not self._settings.face_api_configured:
            raise IdentityUnavailableError("face API credentials are not configured")

        reference_bytes = _decode_image(reference_b64)
        live_bytes = _decode_image(live_b64)
        endpoint = self._settings.FACE_API_ENDPOINT.rstrip("/")
        api_key = self._settings.FACE_API_KEY.get_secret_value()
        threshold = self._settings.FACE_MATCH_THRESHOLD

        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/octet-stream",
        }
        detect_url = f"{endpoint}/face/v1.0/detect"
        verify_url = f"{endpoint}/face/v1.0/verify"

        async with httpx.AsyncClient(timeout=30.0) as client:
            ref_resp = await client.post(
                detect_url,
                params={"returnFaceId": "true"},
                headers=headers,
                content=reference_bytes,
            )
            live_resp = await client.post(
                detect_url,
                params={"returnFaceId": "true"},
                headers=headers,
                content=live_bytes,
            )

        if ref_resp.status_code >= 400 or live_resp.status_code >= 400:
            _logger.warning(
                "face_detect_failed",
                ref_status=ref_resp.status_code,
                live_status=live_resp.status_code,
            )
            raise IdentityUnavailableError("face detection request failed")

        ref_faces = ref_resp.json()
        live_faces = live_resp.json()
        if not ref_faces or not live_faces:
            return FaceMatchResult(score=0.0, matched=False)

        async with httpx.AsyncClient(timeout=30.0) as client:
            verify_resp = await client.post(
                verify_url,
                headers={
                    "Ocp-Apim-Subscription-Key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "faceId1": ref_faces[0]["faceId"],
                    "faceId2": live_faces[0]["faceId"],
                },
            )

        if verify_resp.status_code >= 400:
            _logger.warning("face_verify_failed", status=verify_resp.status_code)
            raise IdentityUnavailableError("face verify request failed")

        payload = verify_resp.json()
        confidence = float(payload.get("confidence", 0.0))
        is_identical = bool(payload.get("isIdentical", False))
        matched = is_identical or confidence >= threshold
        return FaceMatchResult(score=confidence, matched=matched)


def get_face_match_provider() -> FaceMatchProvider:
    """Return the configured face-match provider."""
    from app.proctoring.hf_face import HuggingFaceArcFaceMatchProvider

    settings = get_proctoring_settings()
    provider = settings.FACE_PROVIDER

    if provider == "azure":
        return AzureFaceMatchProvider(settings)
    if provider == "huggingface":
        return HuggingFaceArcFaceMatchProvider(settings)

    if settings.hf_face_configured:
        return HuggingFaceArcFaceMatchProvider(settings)
    if settings.face_api_configured:
        return AzureFaceMatchProvider(settings)
    return HuggingFaceArcFaceMatchProvider(settings)
