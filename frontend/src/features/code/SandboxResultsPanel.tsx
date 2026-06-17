import type { SubmissionRead } from "@/lib/api";

function formatScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return `${(score * 100).toFixed(0)}%`;
}

export interface SandboxResultsPanelProps {
  result: SubmissionRead;
  title?: string;
  subtitle?: string;
}

export function SandboxResultsPanel({
  result,
  title = "Sandbox results",
  subtitle,
}: SandboxResultsPanelProps) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        result.passed
          ? "border-success/30 bg-success/5"
          : "border-error/30 bg-error/5"
      }`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
          {title}
        </p>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            result.passed
              ? "bg-success/15 text-success"
              : "bg-error/15 text-error"
          }`}
        >
          {result.passed ? "Passed" : "Failed"}
        </span>
        <span className="text-sm font-medium">
          Score: {formatScore(result.score)}
        </span>
        <span className="text-sm text-neutral/70">
          {result.passed_tests}/{result.total_tests} tests passed
          {result.hidden_tests_count > 0 &&
            ` · ${result.hidden_tests_count} hidden`}
        </span>
      </div>

      {subtitle && <p className="mt-2 text-xs text-neutral/60">{subtitle}</p>}

      {result.error && (
        <p className="mt-2 text-sm text-error">{result.error}</p>
      )}

      {result.test_results.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral/60">
            Visible test results
          </p>
          {result.test_results
            .filter((tc) => tc.expected_output || tc.error)
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
