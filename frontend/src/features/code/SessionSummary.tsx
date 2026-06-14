"use client";

import type { SubmissionRead } from "@/lib/api";

export interface SessionSummaryProps {
  submissions: SubmissionRead[];
  challengeTitles?: Record<number, string>;
}

export function SessionSummary({ submissions, challengeTitles = {} }: SessionSummaryProps) {
  if (submissions.length === 0) {
    return null;
  }

  const avgScore =
    submissions.reduce((sum, item) => sum + (item.evaluation_score ?? 0), 0) /
    submissions.length;

  return (
    <div className="rounded-lg border border-border bg-surface-muted p-4 text-sm">
      <p className="font-semibold text-neutral">
        Session summary · {submissions.length} challenge
        {submissions.length === 1 ? "" : "s"} graded
      </p>
      <p className="mt-1 text-neutral/70">
        Average score: {avgScore.toFixed(0)}/100 ·{" "}
        {submissions.filter((s) => s.passed).length}/{submissions.length} passed
      </p>
      <ul className="mt-3 space-y-2">
        {submissions.map((item) => (
          <li
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-white px-3 py-2"
          >
            <span className="font-medium">
              {challengeTitles[item.challenge_id] ?? `Challenge #${item.challenge_id}`}
            </span>
            <span className={item.passed ? "text-success" : "text-error"}>
              {item.evaluation_status ?? (item.passed ? "Passed" : "Failed")} ·{" "}
              {item.evaluation_score ?? Math.round((item.score ?? 0) * 100)}/100
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
