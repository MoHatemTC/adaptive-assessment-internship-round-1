"""
Grading layer for the diagram/image feature.

Responsibility: take a learner's raw answer to a visual question and produce
a validated, dimension-scored grade. Two steps, both silent (never shown to
the learner mid-session):

  1. rubric grader  -> LLM scores the answer against the stored rubric
  2. LLM judge      -> second LLM call checks the grader's output for
                        hallucination / inconsistency before it's trusted

Consumes:  DiagramToolOutput (from the examiner agent's tool call)
Produces:  GradeResult (consumed by evaluation_memory.py)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from litellm import acompletion  # routed through the LiteLLM gateway


DIMENSIONS = ["thinking", "soft", "work", "digital_ai", "growth"]


class JudgeVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class Rubric:
    rubric_id: str
    question_id: str
    criteria_text: str                     # what a correct answer covers
    dimension_weights: dict[str, float]     # which of the 5 dims this question scores, and how much
    max_score: float = 1.0


@dataclass(frozen=True)
class DiagramToolOutput:
    """Mirrors the examiner agent's tool output contract (Phase 0.2)."""
    session_id: str
    question_id: str
    image_url: str
    raw_answer_text: str
    timestamp: datetime


@dataclass(frozen=True)
class GradeResult:
    session_id: str
    question_id: str
    dimension_scores: dict[str, float]   # 0-1 per dimension actually weighted by this question
    reasoning: str
    grader_confidence: float             # 0-1, self-reported by the grading LLM
    judge_verdict: JudgeVerdict
    judge_notes: str
    graded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_trusted(self) -> bool:
        return self.judge_verdict is JudgeVerdict.PASS


GRADER_SYSTEM_PROMPT = """You are a silent rubric grader for an adaptive assessment.
Score the learner's answer to a visual/diagram question strictly against the
provided rubric criteria. Do not be lenient or encouraging — score what was
actually demonstrated. Respond ONLY with JSON, no preamble, no markdown fences:
{"dimension_scores": {"<dim>": <0-1 float>, ...}, "reasoning": "<2-3 sentences>", "confidence": <0-1 float>}
Only include dimensions present in the rubric's dimension_weights keys."""

JUDGE_SYSTEM_PROMPT = """You are a grading auditor. You will see a rubric, a
learner's answer, and a grader's proposed scores + reasoning. Check for:
- hallucinated claims not supported by the answer text
- scores inconsistent with the stated reasoning
- reasoning that doesn't actually reference the rubric criteria
Respond ONLY with JSON: {"verdict": "pass" or "fail", "notes": "<1-2 sentences>"}"""


async def _call_grader(rubric: Rubric, answer: DiagramToolOutput) -> dict[str, Any]:
    user_payload = {
        "rubric_criteria": rubric.criteria_text,
        "scored_dimensions": list(rubric.dimension_weights.keys()),
        "learner_answer": answer.raw_answer_text,
    }
    resp = await acompletion(
        model="diagram-grader",          # LiteLLM gateway alias, Phase 0.3
        messages=[
            {"role": "system", "content": GRADER_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        timeout=10,
        num_retries=2,
    )
    return json.loads(resp.choices[0].message.content)


async def _call_judge(rubric: Rubric, answer: DiagramToolOutput, grader_out: dict[str, Any]) -> dict[str, Any]:
    user_payload = {
        "rubric_criteria": rubric.criteria_text,
        "learner_answer": answer.raw_answer_text,
        "grader_scores": grader_out["dimension_scores"],
        "grader_reasoning": grader_out["reasoning"],
    }
    resp = await acompletion(
        model="diagram-judge",
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        timeout=10,
        num_retries=2,
    )
    return json.loads(resp.choices[0].message.content)


def _validate_scores(scores: dict[str, float], rubric: Rubric) -> dict[str, float]:
    """Drop any dimension not in the rubric's scope; clamp to [0,1]."""
    return {
        dim: max(0.0, min(1.0, float(val)))
        for dim, val in scores.items()
        if dim in rubric.dimension_weights
    }


async def grade_visual_answer(rubric: Rubric, answer: DiagramToolOutput) -> GradeResult:
    """Entry point for the Celery task (Phase 7.1). Runs grader then judge."""
    grader_out = await _call_grader(rubric, answer)
    scores = _validate_scores(grader_out["dimension_scores"], rubric)

    judge_out = await _call_judge(rubric, answer, grader_out)
    verdict = JudgeVerdict.PASS if judge_out["verdict"] == "pass" else JudgeVerdict.FAIL

    return GradeResult(
        session_id=answer.session_id,
        question_id=answer.question_id,
        dimension_scores=scores,
        reasoning=grader_out["reasoning"],
        grader_confidence=float(grader_out["confidence"]),
        judge_verdict=verdict,
        judge_notes=judge_out["notes"],
    )