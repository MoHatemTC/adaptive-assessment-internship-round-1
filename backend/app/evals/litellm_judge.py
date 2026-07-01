"""DeepEval judge backed by the Masaar LiteLLM gateway settings."""

from __future__ import annotations

import litellm
from deepeval.models.base_model import DeepEvalBaseLLM

from app.config import Settings, get_settings


class MasaarLiteLLMJudge(DeepEvalBaseLLM):
    """Route DeepEval G-Eval judges through the same LiteLLM config as production."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = self._settings.LITELLM_MODEL

    def load_model(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._model

    def get_model_name(self) -> str:
        return f"masaar-litellm:{self._model}"

    def _completion_kwargs(self) -> dict:
        kwargs: dict = {
            "model": self._model,
            "api_key": self._settings.LITELLM_API_KEY.get_secret_value(),
        }
        if self._settings.LITELLM_BASE_URL:
            kwargs["api_base"] = self._settings.LITELLM_BASE_URL
        return kwargs

    def generate(self, prompt: str) -> str:
        response = litellm.completion(
            messages=[{"role": "user", "content": prompt}],
            **self._completion_kwargs(),
        )
        message = response.choices[0].message
        return (message.content or "").strip()

    async def a_generate(self, prompt: str) -> str:
        response = await litellm.acompletion(
            messages=[{"role": "user", "content": prompt}],
            **self._completion_kwargs(),
        )
        message = response.choices[0].message
        return (message.content or "").strip()


def get_masaar_eval_judge() -> MasaarLiteLLMJudge:
    """Return a judge configured from the current process settings."""
    return MasaarLiteLLMJudge()


__all__ = ["MasaarLiteLLMJudge", "get_masaar_eval_judge"]
