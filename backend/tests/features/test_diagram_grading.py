import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.diagram.evaluation import evaluate_diagram_answer
from app.features.diagram.models import DiagramQuestion, DiagramResponse, DiagramSkillDimension


def _db(response, question):
    response_result = MagicMock()
    response_result.first.return_value = response
    question_result = MagicMock()
    question_result.first.return_value = question
    db = AsyncMock()
    db.exec = AsyncMock(side_effect=[response_result, question_result])
    return db


@pytest.mark.asyncio
async def test_evaluate_calls_memory_agent():
    response = DiagramResponse(id=1, question_id=10, session_id="s1", answer_text="LB", score=1.0)
    question = DiagramQuestion(id=10, svg_content="<svg>[?]</svg>", prompt="Q?", correct_label="Load Balancer", rubric="r", difficulty="easy", dimension=DiagramSkillDimension.digital_ai)
    memory = AsyncMock(return_value=(None, "summary"))
    with patch("app.features.diagram.evaluation.run_memory_agent", new=memory):
        await evaluate_diagram_answer("s1", 0, 1, _db(response, question))
    assert memory.await_args.kwargs["tool_type"] == "diagram"


@pytest.mark.asyncio
async def test_evaluate_missing_response_raises():
    db = _db(None, None)
    with pytest.raises(ValueError, match="DiagramResponse not found"):
        await evaluate_diagram_answer("s1", 0, 999, db)


@pytest.mark.asyncio
async def test_evaluate_missing_question_raises():
    response = DiagramResponse(id=1, question_id=10, session_id="s1", answer_text="LB", score=1.0)
    with pytest.raises(ValueError, match="DiagramQuestion not found"):
        await evaluate_diagram_answer("s1", 0, 1, _db(response, None))


@pytest.mark.asyncio
async def test_evaluate_null_dimension_fallback():
    response = DiagramResponse(id=1, question_id=10, session_id="s1", answer_text="LB", score=1.0)
    question = DiagramQuestion(id=10, svg_content="<svg>[?]</svg>", prompt="Q?", correct_label="Load Balancer", rubric="r", difficulty="easy", dimension=None)
    memory = AsyncMock(return_value=(None, "summary"))
    with patch("app.features.diagram.evaluation.run_memory_agent", new=memory):
        await evaluate_diagram_answer("s1", 0, 1, _db(response, question))
    rubric_scores = json.loads(memory.await_args.kwargs["rubric_scores_json"])
    assert rubric_scores["dimension"] == "thinking"


@pytest.mark.asyncio
async def test_evaluate_passed_at_threshold():
    response = DiagramResponse(id=1, question_id=10, session_id="s1", answer_text="LB", score=1.0)
    question = DiagramQuestion(id=10, svg_content="<svg>[?]</svg>", prompt="Q?", correct_label="Load Balancer", rubric="r", difficulty="easy", dimension=DiagramSkillDimension.thinking)
    memory = AsyncMock(return_value=(None, "summary"))
    with patch("app.features.diagram.evaluation.run_memory_agent", new=memory):
        await evaluate_diagram_answer("s1", 0, 1, _db(response, question))
    assert memory.await_args.kwargs["passed"] is True


@pytest.mark.asyncio
async def test_evaluate_failed_below_threshold():
    response = DiagramResponse(id=1, question_id=10, session_id="s1", answer_text="Firewall", score=0.0)
    question = DiagramQuestion(id=10, svg_content="<svg>[?]</svg>", prompt="Q?", correct_label="Load Balancer", rubric="r", difficulty="easy", dimension=DiagramSkillDimension.thinking)
    memory = AsyncMock(return_value=(None, "summary"))
    with patch("app.features.diagram.evaluation.run_memory_agent", new=memory):
        await evaluate_diagram_answer("s1", 0, 1, _db(response, question))
    assert memory.await_args.kwargs["passed"] is False
