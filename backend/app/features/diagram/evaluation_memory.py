"""
Evaluation memory layer for the diagram/image feature.

Responsibility: turn a trusted GradeResult into a durable, structured
VisualMemoryCard and persist it. This is the only write path into the
per-session memory store that the analysis layer reads from.

Consumes:  GradeResult (from grading.py) — only writes if judge_verdict == PASS
Produces:  VisualMemoryCard, persisted in Qdrant
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from grading import DIMENSIONS, GradeResult, Rubric


@dataclass(frozen=True)
class VisualMemoryCard:
    session_id: str
    question_id: str
    difficulty: int                      # 1-10, the difficulty this question was served at
    topic_tags: tuple[str, ...]
    dimension_scores: dict[str, float]    # only the dims this question actually scored
    grader_confidence: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def point_id(self) -> str:
        return f"{self.session_id}:{self.question_id}"

    def to_payload(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["topic_tags"] = list(self.topic_tags)
        return d


class QdrantWriter(Protocol):
    """Narrow interface so this module stays testable without a live Qdrant client."""
    async def upsert(self, collection: str, point_id: str, vector: list[float], payload: dict) -> None: ...


MEMORY_COLLECTION = "visual_memory_cards"


def _topic_embedding(topic_tags: tuple[str, ...], embed_fn) -> list[float]:
    """Embeds topic tags so the analysis/adaptation layers can do similarity
    lookups later (e.g. 'find weak topics similar to X'). embed_fn is injected
    to keep this module free of a hard embedding-model dependency."""
    return embed_fn(" ".join(topic_tags))


def build_memory_card(
    grade: GradeResult,
    rubric: Rubric,
    difficulty: int,
    topic_tags: tuple[str, ...],
) -> VisualMemoryCard | None:
    """Returns None if the grade isn't trusted — caller should not persist it
    and should instead route to human review / re-grade."""
    if not grade.is_trusted:
        return None

    return VisualMemoryCard(
        session_id=grade.session_id,
        question_id=grade.question_id,
        difficulty=difficulty,
        topic_tags=topic_tags,
        dimension_scores=grade.dimension_scores,
        grader_confidence=grade.grader_confidence,
    )


async def write_memory_card(
    card: VisualMemoryCard,
    writer: QdrantWriter,
    embed_fn,
) -> None:
    vector = _topic_embedding(card.topic_tags, embed_fn)
    await writer.upsert(
        collection=MEMORY_COLLECTION,
        point_id=card.point_id,
        vector=vector,
        payload=card.to_payload(),
    )


async def grade_and_remember(
    grade: GradeResult,
    rubric: Rubric,
    difficulty: int,
    topic_tags: tuple[str, ...],
    writer: QdrantWriter,
    embed_fn,
) -> VisualMemoryCard | None:
    """Convenience wrapper chaining build + persist; mirrors the Celery task
    boundary from Phase 7.1 (grade -> judge -> memory write happens in one
    background job)."""
    card = build_memory_card(grade, rubric, difficulty, topic_tags)
    if card is None:
        return None
    await write_memory_card(card, writer, embed_fn)
    return card