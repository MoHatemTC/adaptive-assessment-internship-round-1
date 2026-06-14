"use client";

import type { ScoreBreakdown, SubmissionRead } from "@/lib/api";

const BREAKDOWN_LABELS: Record<keyof ScoreBreakdown, string> = {
  correctness: "Correctness",
  completeness: "Completeness",
  code_quality: "Code quality",
  performance: "Performance",
  creativity: "Creativity",
  documentation: "Documentation",
};

export interface SubmissionResultsProps {
  result: SubmissionRead;
  className?: string;
}

export function SubmissionResults({ result, className = "" }: SubmissionResultsProps) {
  const passed = result.passed ?? false;

  return (
    <div
      className={`rounded-lg border p-4 ${
        passed ? "border-success/30 bg-success/5" : "border-error/30 bg-error/5"
      } ${className}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            passed ? "bg-success/15 text-success" : "bg-error/15 text-error"
          }`}
        >
          {result.evaluation_status ?? (passed ? "Passed" : "Failed")}
        </span>
        <span className="text-sm font-medium">
          Score:{" "}
          {result.evaluation_score != null
            ? `${result.evaluation_score}/100`
            : `${((result.score ?? 0) * 100).toFixed(0)}%`}
        </span>
        {result.next_difficulty && (
          <span className="text-sm text-neutral/70">Next: {result.next_difficulty}</span>
        )}
        <span className="text-sm text-neutral/70">
          {result.passed_tests}/{result.total_tests} tests passed
          {result.hidden_tests_count > 0 &&
            ` (${result.hidden_tests_count} hidden)`}
        </span>
      </div>

      {result.feedback_summary && (
        <p className="mt-2 text-sm text-neutral/80">{result.feedback_summary}</p>
      )}

      {result.breakdown && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
            Score breakdown
          </p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {(Object.keys(BREAKDOWN_LABELS) as (keyof ScoreBreakdown)[]).map((key) => (
              <div
                key={key}
                className="rounded-md border border-border bg-white px-3 py-2 text-sm"
              >
                <span className="font-medium">{BREAKDOWN_LABELS[key]}</span>
                <span className="ml-2 text-neutral/70">{result.breakdown![key]}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.strengths && result.strengths.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
            Strengths
          </p>
          <ul className="mt-1 list-inside list-disc text-sm text-neutral/80">
            {result.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {result.weaknesses && result.weaknesses.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
            Areas to improve
          </p>
          <ul className="mt-1 list-inside list-disc text-sm text-neutral/80">
            {result.weaknesses.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {result.recommendations && result.recommendations.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
            Recommendations
          </p>
          <ul className="mt-1 list-inside list-disc text-sm text-neutral/80">
            {result.recommendations.map((rec) => (
              <li key={rec}>{rec}</li>
            ))}
          </ul>
        </div>
      )}

      {result.error && <p className="mt-2 text-sm text-error">{result.error}</p>}

      {result.scores.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {result.scores.map((score) => (
            <li key={score.dimension}>
              <span className="font-medium capitalize">{score.dimension}</span>:{" "}
              {(score.score * 100).toFixed(0)}% — {score.feedback}
            </li>
          ))}
        </ul>
      )}

      {result.test_results.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
            Visible test results
          </p>
          {result.test_results
            .filter((tc) => tc.expected_output || tc.error || !tc.passed)
            .map((tc) => (
              <div
                key={tc.test_case_id}
                className="rounded-md border border-border bg-white p-2 text-xs"
              >
                <span
                  className={
                    tc.passed ? "font-medium text-success" : "font-medium text-error"
                  }
                >
                  Test {tc.test_case_id}: {tc.passed ? "pass" : "fail"}
                </span>
                {!tc.passed && tc.expected_output && (
                  <p className="mt-1 text-neutral/70">
                    Expected: <code>{tc.expected_output}</code>
                    {tc.actual_output && (
                      <>
                        {" "}
                        · Got: <code>{tc.actual_output}</code>
                      </>
                    )}
                  </p>
                )}
                {tc.error && (
                  <pre className="mt-1 overflow-x-auto text-error">{tc.error}</pre>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
