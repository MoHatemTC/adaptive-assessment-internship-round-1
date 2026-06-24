"""Local sentence embedding utility for Qdrant vector storage."""
from __future__ import annotations

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_model = None


def get_embedding_model():
    """Return singleton SentenceTransformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info(
            "embedding_model_loaded",
            model=settings.EMBEDDING_MODEL,
        )
    return _model


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a list of floats.

    Blocking (CPU-bound). Call from async code via ``asyncio.to_thread``.
    """
    model = get_embedding_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()
