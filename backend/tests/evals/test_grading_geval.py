"""DeepEval G-Eval checks for silent grading rubrics (opt-in live LLM judge)."""

from __future__ import annotations

import os

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

from app.evals.grading_geval import (
    build_rubric_coherence_metric,
    build_rubric_fairness_metric,
    voice_grading_input,
)
from app.evals.grading_goldens import VOICE_GRADING_GOLDENS

pytestmark = pytest.mark.deepeval

_RUN_DEEPEVAL = os.environ.get("RUN_DEEPEVAL", "").strip() == "1"
_SKIP_REASON = "Set RUN_DEEPEVAL=1 and configure LITELLM_API_KEY to run G-Eval judge tests"


def test_voice_grading_golden_catalog_has_bands():
    bands = {g.quality_band for g in VOICE_GRADING_GOLDENS}
    assert "strong" in bands
    assert "weak" in bands


@pytest.mark.parametrize("golden", VOICE_GRADING_GOLDENS, ids=lambda g: g.quality_band)
@pytest.mark.skipif(not _RUN_DEEPEVAL, reason=_SKIP_REASON)
def test_voice_reference_rubric_passes_geval(golden):
    """Reference rubrics in our golden set should pass fairness + coherence G-Eval."""
    test_case = LLMTestCase(
        input=voice_grading_input(
            golden.question,
            golden.transcript,
            golden.difficulty,
        ),
        actual_output=golden.rubric_json,
    )
    assert_test(
        test_case,
        [
            build_rubric_coherence_metric(),
            build_rubric_fairness_metric(),
        ],
    )
