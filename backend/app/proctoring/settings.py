"""Proctoring-specific environment configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

FaceProviderName = Literal["azure", "huggingface", "auto"]


class ProctoringSettings(BaseSettings):
    """Face API and dev fallback settings for the proctoring feature.

    Attributes:
        FACE_PROVIDER: ``azure``, ``huggingface``, or ``auto`` (pick HF, then Azure).
        FACE_API_ENDPOINT: Azure Face API base URL.
        FACE_API_KEY: Azure subscription key.
        HF_TOKEN: Hugging Face token for gated model downloads (optional for public models).
        HF_FACE_MODEL_REPO: Hugging Face repo hosting the ArcFace ONNX weights.
        HF_FACE_MODEL_FILE: ONNX filename inside the repo.
        FACE_MATCH_THRESHOLD: Minimum cosine similarity (0–1) to treat two faces as a match.
        PROCTORING_HIGH_SEVERITY_THRESHOLD: Dev fallback when assessment config omits a threshold.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    FACE_PROVIDER: FaceProviderName = "auto"
    FACE_API_ENDPOINT: str = ""
    FACE_API_KEY: SecretStr = SecretStr("")
    HF_TOKEN: SecretStr = SecretStr("")
    HF_FACE_MODEL_REPO: str = "onnx-community/arcface-onnx"
    HF_FACE_MODEL_FILE: str = "arcface.onnx"
    FACE_MATCH_THRESHOLD: float = 0.7
    PROCTORING_HIGH_SEVERITY_THRESHOLD: int = 3

    @property
    def face_api_configured(self) -> bool:
        """Whether Azure Face credentials are present."""
        return bool(self.FACE_API_ENDPOINT.strip()) and bool(
            self.FACE_API_KEY.get_secret_value().strip()
        )

    @property
    def hf_face_configured(self) -> bool:
        """Whether Hugging Face ArcFace verification can run."""
        return bool(self.HF_FACE_MODEL_REPO.strip()) and bool(
            self.HF_FACE_MODEL_FILE.strip()
        )


@lru_cache
def get_proctoring_settings() -> ProctoringSettings:
    """Return cached proctoring settings."""
    return ProctoringSettings()
