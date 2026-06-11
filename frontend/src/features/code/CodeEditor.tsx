"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import {
  createCodeSubmission,
  type ChallengeRead,
  type SubmissionRead,
} from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center rounded-lg border border-border bg-surface-muted text-sm text-neutral">
      Loading editor…
    </div>
  ),
});

export interface CodeEditorProps {
  challenge: ChallengeRead;
  sessionId: string;
  onSubmitted?: (result: SubmissionRead) => void;
}

export function CodeEditor({ challenge, sessionId, onSubmitted }: CodeEditorProps) {
  const [code, setCode] = useState(challenge.starter_code);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmissionRead | null>(null);

  const handleSubmit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const submission = await createCodeSubmission({
        challenge_id: challenge.id,
        session_id: sessionId,
        submitted_code: code,
      });
      setResult(submission);
      onSubmitted?.(submission);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setLoading(false);
    }
  }, [challenge.id, code, onSubmitted, sessionId]);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-neutral">{challenge.title}</h2>
        <p className="mt-1 text-sm text-neutral/80">{challenge.description}</p>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <MonacoEditor
          height="320px"
          language={challenge.language}
          theme="vs-light"
          value={code}
          onChange={(value) => setCode(value ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={loading || !code.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running…" : "Run / Submit"}
        </button>
        {error && (
          <p className="text-sm text-error" role="alert">
            {error}
          </p>
        )}
      </div>

      {result && (
        <div
          className={`rounded-lg border p-4 ${
            result.passed
              ? "border-success/30 bg-success/5"
              : "border-error/30 bg-error/5"
          }`}
        >
          <div className="flex flex-wrap items-center gap-3">
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
              Score: {((result.score ?? 0) * 100).toFixed(0)}%
            </span>
            <span className="text-sm text-neutral/70">
              {result.passed_tests}/{result.total_tests} tests passed
            </span>
          </div>

          {result.error && (
            <p className="mt-2 text-sm text-error">{result.error}</p>
          )}

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
                .filter((tc) => tc.expected_output || tc.error)
                .map((tc) => (
                  <div
                    key={tc.test_case_id}
                    className="rounded-md border border-border bg-white p-2 text-xs"
                  >
                    <span
                      className={
                        tc.passed ? "text-success font-medium" : "text-error font-medium"
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
      )}
    </div>
  );
}
