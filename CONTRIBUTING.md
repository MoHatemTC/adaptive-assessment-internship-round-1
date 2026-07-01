# Contributing

## Branch strategy

| Branch | Purpose |
|---|---|
| `main` | Demo-ready. PRs only. |
| `voice-agent` | Voice interview |
| `mcq-tool` | MCQ protocol tool |
| `viz-tool` | Diagram / image reasoning tool |
| `avatar-tool` | Camera-on interview tool |
| `coding-tool` | E2B code execution tool |

## Rules
- Never modify `app/core/` — kernel is READ-ONLY **except** when extending the documented LLM/STT gateways below.
- New env vars must be added to `.env.example`.

## LLM and observability call paths (P2-A3)

| Path | Module | Use when |
|------|--------|----------|
| Text chat / structured LLM | `app.core.llm` (`get_llm_with_tracing`, `llm_invoke_config`) | Default for all text generation and grading |
| Speech-to-text | `app.core.stt` (`atranscribe_audio`) | Voice chunks and any future audio transcription |
| Vision / multimodal JSON | `app.core.vision` (`acompletion_vision_json`) | Diagram image grading, proctoring VLM (`proctoring/vlm_face.py`) |

Do **not** call `litellm.acompletion` or `litellm.atranscription` from feature code. The vision and STT modules are the only approved bypasses; they include retry and metrics (and Langfuse where applicable).
