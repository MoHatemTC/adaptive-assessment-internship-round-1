import base64
import inspect
import uuid
from typing import Optional

import litellm
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.config import get_settings

from app.core.logging import get_logger
from app.features.diagram.models import Diagram

_logger = get_logger(__name__)

def _resolve_model_name(model: Optional[str]) -> str:
    """
    Resolve a model override, falling back to the configured default model.
    """
    candidate = (model or "").strip()
    if candidate:
        return candidate
    return get_settings().LITELLM_MODEL


def _render_image_fallback(prompt: str) -> str:
    """Return a lightweight fallback image URL when generation fails."""
    fallback_svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1024' height='1024'>"
        "<rect width='100%' height='100%' fill='#2d3748'/>"
        "<text x='50%' y='48%' text-anchor='middle' fill='#e2e8f0' font-family='Arial,Helvetica,sans-serif' font-size='48'>"
        "Diagram unavailable</text>"
        "<text x='50%' y='58%' text-anchor='middle' fill='#cbd5e1' font-family='Arial,Helvetica,sans-serif' font-size='32'>"
        "Please try again later</text>"
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(
        fallback_svg.encode("utf-8")
    ).decode("ascii")


def _get_image_url_from_response(response: object) -> Optional[str]:
    if getattr(response, "data", None):
        first_item = response.data[0]
        if getattr(first_item, "url", None):
            return first_item.url
        if getattr(first_item, "b64_json", None):
            return f"data:image/png;base64,{first_item.b64_json}"

    if getattr(response, "url", None):
        return response.url

    return None


async def _generate_ai_image_url(prompt: str, model: str) -> str:
    settings = get_settings()
    response = litellm.image_generation(
        prompt=prompt,
        model=model,
        response_format="url",
        size="1024x1024",
        api_key=settings.LITELLM_API_KEY.get_secret_value(),
        api_base=settings.LITELLM_BASE_URL or None,
    )

    if inspect.isawaitable(response):
        response = await response  # type: ignore

    image_url = _get_image_url_from_response(response)
    if not image_url:
        raise ValueError("Image generation returned no URL")
    return image_url


class DiagramService:
    async def create_diagram(
        self,
        db: AsyncSession,
        prompt: str,
        user_id: Optional[uuid.UUID] = None,
        model: Optional[str] = None,
    ) -> Diagram:
        """
        Create a diagram record, request an AI-generated image, persist it,
        and return the diagram metadata.
        """
        # 1. Resolve model and create a pending diagram record
        resolved_model = _resolve_model_name(model)
        diagram = Diagram(
            prompt=prompt,
            user_id=user_id,
            model_name=resolved_model,
            status="pending",
        )
        db.add(diagram)
        await db.flush()

        # 2. Generate an image using LiteLLM
        try:
            image_url = await _generate_ai_image_url(prompt, resolved_model)
            diagram.image_url = image_url
            diagram.status = "completed"
        except Exception as exc:
            _logger.error("diagram_image_generation_failed", error=str(exc))
            diagram.image_url = _render_image_fallback(prompt)
            diagram.status = "failed"

        db.add(diagram)
        await db.flush()
        return diagram

    async def get_diagram(
        self,
        db: AsyncSession,
        diagram_id: uuid.UUID,
    ) -> Optional[Diagram]:
        """
        Retrieve a diagram record from the database by ID.
        """
        result = await db.exec(select(Diagram).where(Diagram.id == diagram_id))
        return result.first()

    async def list_user_diagrams(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[Diagram]:
        """
        Retrieve all diagrams generated for a specific user.
        """
        result = await db.exec(select(Diagram).where(Diagram.user_id == user_id))
        return list(result.all())