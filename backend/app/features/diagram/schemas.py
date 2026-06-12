from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class DiagramCreateRequest(BaseModel):
    prompt: str = Field(
        ...,
        description="Text description or instructions for the diagram to generate",
    )
    user_id: Optional[UUID] = Field(
        default=None,
        description="Optional ID of the learner requesting the diagram",
    )
    model: Optional[str] = Field(
        default=None,
        description="Optional LLM model override used for diagram generation",
    )


class DiagramResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    prompt: str
    model_name: str
    image_url: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True