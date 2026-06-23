"use client";

import type { ChallengeRead, DifficultyLevel } from "@/lib/api";

import { difficultyLabel } from "@/features/code/types";

export interface CodeQuestionPanelProps {
  challenge: ChallengeRead;
  difficulty: DifficultyLevel;
}

export function CodeQuestionPanel({ challenge, difficulty }: CodeQuestionPanelProps) {
  return (
    <section className="flex flex-1 flex-col gap-sm">
      <div className="flex flex-col gap-sm rounded-xl border border-surface-container-highest bg-surface p-md shadow-card">
        <div className="flex items-start justify-between gap-sm">
          <h1 className="text-headline-sm text-on-surface">{challenge.title}</h1>
          <span className="shrink-0 rounded-full bg-primary-container px-3 py-1 text-label-sm text-on-primary-container">
            {difficultyLabel(difficulty)}
          </span>
        </div>
        <div className="flex flex-col gap-4 text-body-md text-on-surface-variant">
          <p className="whitespace-pre-wrap">{challenge.description}</p>
        </div>
      </div>

      <div className="flex items-start gap-sm rounded-xl border border-surface-container-highest bg-surface-container-low p-sm">
        <span className="material-symbols-outlined mt-1 text-primary">lightbulb</span>
        <div>
          <h3 className="mb-1 text-label-md text-on-surface">Hint</h3>
          <p className="text-body-sm text-on-surface-variant">
            Use <code className="rounded bg-surface px-1">Run Code</code> to test
            in the sandbox before submitting. Your official answer is graded
            silently after submit.
          </p>
        </div>
      </div>
    </section>
  );
}
