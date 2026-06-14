"use client";

import type { RunRead } from "@/lib/api";

export function RunResults({ result }: { result: RunRead }) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface-muted p-4 text-sm">
      <p>
        <span className="font-semibold">Run outcome:</span> {result.outcome} ·{" "}
        {result.passed_tests}/{result.total_tests} visible tests passed · Run #{result.run_count}
      </p>
      {result.error && (
        <p className="text-error" role="alert">
          {result.error}
        </p>
      )}
      {result.test_results.length > 0 && (
        <ul className="space-y-2">
          {result.test_results.map((tr) => (
            <li
              key={tr.test_case_id}
              className={`rounded-md border px-3 py-2 ${
                tr.passed ? "border-success/30 bg-white" : "border-error/30 bg-white"
              }`}
            >
              <span className="font-medium">{tr.passed ? "Pass" : "Fail"}</span>
              {!tr.passed && tr.expected_output && (
                <span className="ml-2 text-neutral/70">
                  expected &quot;{tr.expected_output}&quot;, got &quot;{tr.actual_output}&quot;
                </span>
              )}
              {tr.error && <pre className="mt-1 overflow-x-auto text-xs text-error">{tr.error}</pre>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
