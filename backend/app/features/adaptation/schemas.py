"""
app/features/adaptation/schemas.py
Tool-agnostic shapes. Every feature (diagram, mcq, voice, code) must
normalize its answers into AnswerRecord before the agent sees them.
"""

import uuid
from typing import Literal
from pydantic import BaseModel, Field

ToolName = Literal["diagram", "mcq", "voice", "camera", "code"]

DimensionName = Literal["thinking", "soft", "work", "digital_ai", "growth"]

Difficulty = Literal["easy", "medium", "hard"]


class AnswerRecord(BaseModel):
    """
    One normalized answer, regardless of which tool produced it.
    Every feature's repository function must return a list of these.
    """
    tool:      ToolName
    dimension: DimensionName
    score:     float = Field(..., ge=0.0, le=1.0)   # always normalized 0.0-1.0
    feedback:  str = ""


class AdaptationInput(BaseModel):
    session_id: uuid.UUID


class DimensionScore(BaseModel):
    score:    int = Field(..., ge=1, le=10)
    feedback: str


class AdaptationResult(BaseModel):
    session_id:       uuid.UUID
    next_difficulty:  Difficulty
    dimension_scores: dict[DimensionName, DimensionScore]