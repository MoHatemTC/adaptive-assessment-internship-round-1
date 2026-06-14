"""
schemas.py — Pydantic v2 request/response models for the diagram feature.

DiagramQuestionResponse : what GET /diagram/{id} returns to the frontend
                          includes the served image URL (not a raw path)
DiagramAnswerRequest    : body for POST /diagram/{id}/answer
DiagramAnswerResponse   : what the submit route returns to the agent
                          — structured grading result, never shown to learner
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl

from app.features.diagram.models import Difficulty, SkillDimension


class DiagramQuestionResponse(BaseModel):
    id:         uuid.UUID
    image_url:  str
    prompt:     str
    difficulty: Difficulty
    dimension:  SkillDimension

    model_config = {"from_attributes": True}


class DiagramAnswerRequest(BaseModel):
    session_id:  uuid.UUID = Field(..., description="Blueprint session tracking ID")
    answer_text: str       = Field(..., min_length=1, max_length=4000)


class DiagramAnswerResponse(BaseModel):
    """
    Structured grading result returned to the agent.
    Score and feedback are silent — not forwarded to the learner mid-session.
    The agent uses `score` and `dimension` to select the next question difficulty.
    """
    answer_id:        uuid.UUID
    session_id:       uuid.UUID
    question_id:      uuid.UUID
    score:            float
    dimension:        SkillDimension
    grading_feedback: str
    graded_at:        datetime