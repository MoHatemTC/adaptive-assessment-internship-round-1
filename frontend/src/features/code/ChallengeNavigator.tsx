"use client";

import type { SessionChallengeRead } from "@/lib/api";

export interface ChallengeNavigatorProps {
  challenges: SessionChallengeRead[];
  selectedId: number;
  onSelect: (challengeId: number) => void;
}

export function ChallengeNavigator({
  challenges,
  selectedId,
  onSelect,
}: ChallengeNavigatorProps) {
  if (challenges.length <= 1) {
    return null;
  }

  return (
    <nav
      className="flex flex-wrap gap-2"
      aria-label="Assessment challenges"
    >
      {challenges.map((challenge) => {
        const active = challenge.challenge_id === selectedId;
        return (
          <button
            key={challenge.challenge_id}
            type="button"
            onClick={() => onSelect(challenge.challenge_id)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              active
                ? "bg-primary text-white"
                : "bg-surface-muted text-neutral hover:bg-surface-muted/80"
            }`}
            aria-current={active ? "step" : undefined}
          >
            <span className="font-semibold">{challenge.position}</span>
            <span className="mx-1 text-neutral/40">/</span>
            <span>{challenge.challenge_count}</span>
            <span className="mx-1.5">·</span>
            {challenge.title}
            <span className="ml-1.5 rounded bg-white/20 px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
              {challenge.language}
            </span>
            {challenge.submitted ? " ✓" : ""}
          </button>
        );
      })}
    </nav>
  );
}
