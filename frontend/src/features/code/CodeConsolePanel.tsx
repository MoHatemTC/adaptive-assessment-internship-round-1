"use client";

import type { SubmissionRead } from "@/lib/api";

export interface ConsoleLine {
  id: string;
  tone: "info" | "success" | "error" | "muted";
  text: string;
}

export interface CodeConsolePanelProps {
  lines: ConsoleLine[];
  onClear: () => void;
}

function toneClass(tone: ConsoleLine["tone"]): string {
  switch (tone) {
    case "success":
      return "text-success";
    case "error":
      return "text-error";
    case "info":
      return "text-sky-300";
    default:
      return "text-gray-400";
  }
}

export function submissionToConsoleLines(result: SubmissionRead): ConsoleLine[] {
  const lines: ConsoleLine[] = [
    {
      id: "summary",
      tone: result.passed ? "success" : "error",
      text: result.passed
        ? `Passed ${result.passed_tests}/${result.total_tests} visible tests.`
        : `Failed ${result.passed_tests}/${result.total_tests} visible tests.`,
    },
  ];

  if (result.error) {
    lines.push({ id: "error", tone: "error", text: result.error });
  }

  for (const tc of result.test_results) {
    if (!tc.expected_output && !tc.error) continue;
    lines.push({
      id: `tc-${tc.test_case_id}`,
      tone: tc.passed ? "success" : "error",
      text: tc.error
        ? `Test ${tc.test_case_id}: ${tc.error}`
        : `Test ${tc.test_case_id}: expected ${tc.expected_output}, got ${tc.actual_output || "(empty)"}`,
    });
  }

  return lines;
}

export function CodeConsolePanel({ lines, onClear }: CodeConsolePanelProps) {
  return (
    <div className="flex h-48 flex-col overflow-hidden rounded-xl border border-editor-border bg-editor-header">
      <div className="flex items-center justify-between border-b border-editor-border bg-[#11141A] px-sm py-2">
        <span className="flex items-center gap-1 text-label-sm text-gray-300">
          <span className="material-symbols-outlined text-[16px]">terminal</span>
          Console Output
        </span>
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear Console"
          className="text-label-sm text-gray-500 transition hover:text-white"
        >
          Clear
        </button>
      </div>
      <div className="flex flex-1 flex-col gap-1 overflow-y-auto p-sm font-mono text-xs">
        {lines.length === 0 ? (
          <div className="text-sky-300">
            Ready. Click &apos;Run Code&apos; to execute.
          </div>
        ) : (
          lines.map((line) => (
            <div key={line.id} className={toneClass(line.tone)}>
              {line.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
