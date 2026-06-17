"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import {
  createAdaptiveCodeSubmission,
  getCodeSubmission,
  type AdaptiveContract,
  type ChallengeRead,
  type DifficultyLevel,
  type LlmRubricSummary,
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
  assessmentId: string;
  questionIndex: number;
  difficulty: DifficultyLevel;
  disabled?: boolean;
  onSubmitted?: (result: {
    submission: SubmissionRead;
    contract: AdaptiveContract;
    llmRubric: LlmRubricSummary | null;
  }) => void;
}

function formatScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return `${(score * 100).toFixed(0)}%`;
}

function LlmRubricPanel({ rubric }: { rubric: LlmRubricSummary }) {
  return (
    <div className="rounded-lg border border-secondary/15 bg-surface-muted p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-secondary">
        LLM rubric (approach &amp; efficiency)
      </p>
      <p className="mt-2 text-sm font-medium text-neutral">
        Overall qualitative score: {(rubric.overall * 100).toFixed(0)}%
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-md bg-white p-3 text-sm shadow-sm">
          <p className="font-medium text-neutral">
            Approach ({(rubric.approach_score * 100).toFixed(0)}%)
          </p>
          <p className="mt-1 text-neutral/80">{rubric.approach_feedback}</p>
        </div>
        <div className="rounded-md bg-white p-3 text-sm shadow-sm">
          <p className="font-medium text-neutral">
            Efficiency ({(rubric.efficiency_score * 100).toFixed(0)}%)
          </p>
          <p className="mt-1 text-neutral/80">{rubric.efficiency_feedback}</p>
        </div>
      </div>
    </div>
  );
}

function ContractPanel({ contract }: { contract: AdaptiveContract }) {
  const scores = contract.cumulative_scores;
  const engaged = (
    [
      ["thinking", scores.thinking],
      ["work", scores.work],
      ["digital_ai", scores.digital_ai],
    ] as const
  ).filter(([, value]) => value != null);

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-primary">
        Adaptive contract (LLM loop)
      </p>
      {contract.stop ? (
        <p className="mt-2 text-sm font-medium text-neutral">
          Session complete — no further coding questions.
        </p>
      ) : (
        <p className="mt-2 text-sm text-neutral">
          Next question:{" "}
          <span className="font-medium capitalize">{contract.difficulty}</span>
          {contract.focus_dimension && (
            <>
              {" "}
              · focus{" "}
              <span className="font-medium">
                {contract.focus_dimension.replace("_", " ")}
              </span>
            </>
          )}
        </p>
      )}
      {contract.memory_summary && (
        <p className="mt-2 text-sm text-neutral/80">{contract.memory_summary}</p>
      )}
      {engaged.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2 text-xs">
          {engaged.map(([name, value]) => (
            <li
              key={name}
              className="rounded-full bg-white px-2.5 py-1 font-medium text-neutral shadow-sm"
            >
              {name.replace("_", " ")}: {value}/10
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CodeEditor({
  challenge,
  sessionId,
  assessmentId,
  questionIndex,
  difficulty,
  disabled = false,
  onSubmitted,
}: CodeEditorProps) {
  const [code, setCode] = useState(challenge.starter_code);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SubmissionRead | null>(null);
  const [contract, setContract] = useState<AdaptiveContract | null>(null);
  const [llmRubric, setLlmRubric] = useState<LlmRubricSummary | null>(null);

  const handleSubmit = useCallback(async () => {
    setLoading(true);
    setError(null);
    setContract(null);
    setLlmRubric(null);
    try {
      const adaptive = await createAdaptiveCodeSubmission({
        challenge_id: challenge.id,
        session_id: sessionId,
        assessment_id: assessmentId,
        submitted_code: code,
        question_index: questionIndex,
        difficulty,
      });
      const submission = await getCodeSubmission(adaptive.submission_id);
      setResult(submission);
      setContract(adaptive.contract);
      setLlmRubric(adaptive.llm_rubric);
      onSubmitted?.({
        submission,
        contract: adaptive.contract,
        llmRubric: adaptive.llm_rubric,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setLoading(false);
    }
  }, [
    assessmentId,
    challenge.id,
    code,
    difficulty,
    onSubmitted,
    questionIndex,
    sessionId,
  ]);

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-neutral">{challenge.title}</h2>
        <p className="mt-1 text-sm text-neutral/80">{challenge.description}</p>
        <p className="mt-2 text-xs text-neutral/60">
          Question {questionIndex + 1} · {difficulty} · runs E2B sandbox + LLM
          grading
        </p>
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
          disabled={loading || disabled || !code.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running sandbox + LLM loop…" : "Submit (adaptive)"}
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
              Sandbox score: {formatScore(result.score)}
            </span>
            <span className="text-sm text-neutral/70">
              {result.passed_tests}/{result.total_tests} tests passed
            </span>
          </div>

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

      {llmRubric && <LlmRubricPanel rubric={llmRubric} />}

      {contract && <ContractPanel contract={contract} />}
    </div>
  );
}
