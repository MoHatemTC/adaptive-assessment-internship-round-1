"""Pydantic schemas for session radar reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.shared.schemas.proctoring import SessionIntegritySnapshot
from app.shared.schemas.memory import DimensionName

_DIMENSION_LABELS: dict[DimensionName, str] = {
    "thinking": "Reasoning",
    "soft": "Communication",
    "work": "Execution",
    "digital_ai": "Digital & AI",
    "growth": "Growth mindset",
}


class DimensionRadarPoint(BaseModel):
    """One spoke on the five-dimension radar chart."""

    name: DimensionName
    label: str
    score: int | None = Field(
        None,
        ge=1,
        le=10,
        description="Whole integer 1–10, or null when not assessed",
    )


class SessionRadarReport(BaseModel):
    """Learner- and admin-safe session report (no rubric text or raw grades)."""

    session_id: str
    dimensions: list[DimensionRadarPoint]
    overall_score: int | None = Field(
        None,
        ge=1,
        le=10,
        description="Rounded mean of non-null dimension scores",
    )
    questions_answered: int
    tools_used: list[str]
    strengths: list[str]
    growth_areas: list[str]
    evidence_highlights: list[str]
    summary: str
    generated_at: datetime
    integrity: SessionIntegritySnapshot | None = None


def dimension_label(name: DimensionName) -> str:
    """Human-readable label for a dimension key."""
    return _DIMENSION_LABELS[name]
