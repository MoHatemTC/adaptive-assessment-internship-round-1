# Coding tool — frontend

Stitch-aligned UI for the adaptive coding challenge (`coding_challenge_masaar`).
Designed as a **standalone slice** at `/code` and as an **embeddable tool** for
the examiner chat / assessment shell.

## Routes

| Route | Purpose |
|-------|---------|
| `/code` | Standalone demo — language picker then adaptive loop |
| `/code?challenge_id=1` | Load a fixed challenge (no LLM generation) |
| `/code?session_id=…&assessment_id=…` | Pre-wire platform session ids |

## Embed in the assessment shell

```tsx
import { CodeChallengeView } from "@/features/code";

<CodeChallengeView
  mode="embedded"
  sessionId={platformSessionId}
  assessmentId={assessmentId}
  questionNumber={blueprintIndex + 1}
  totalQuestions={blueprint.coding.max_questions}
  timeLimitSeconds={challenge.time_limit_seconds}
  initialLanguage="python"
  autoStart
  onExit={() => router.push(`/assessment/${token}`)}
  onSessionComplete={(summary) => examiner.advance(summary)}
  onSubmitted={({ contract }) => proctoring.track(contract)}
/>
```

## Design system

Tokens follow [`ExtraDocs/stitch_masaar_voice_assessment_ui/design.md`](../../../ExtraDocs/stitch_masaar_voice_assessment_ui/design.md)
and the `coding_challenge_masaar` mockup:

- Plus Jakarta Sans (root layout)
- Material Symbols Outlined (header, buttons, hint)
- Two-column layout: question left, editor + console right
- Dark Monaco theme (`vs-dark`) in the editor card

## Silent learner session

- **Run Code** — sandbox only; output in the console panel
- **Submit Solution** — adaptive submit; no rubric/score/memory shown
- Grading and memory cards are persisted server-side only

## API contract

All calls go through [`src/lib/api.ts`](../../lib/api.ts) under `/api/v1/code/*`.
Types mirror backend `AdaptiveContract` and `ChallengeRead`.
