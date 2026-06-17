"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import { SandboxResultsPanel } from "@/features/code/SandboxResultsPanel";
import {
  createAdaptiveCodeSubmission,
  createCodeSubmission,
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
  const [runningTests, setRunningTests] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<SubmissionRead | null>(null);
  const [submitResult, setSubmitResult] = useState<SubmissionRead | null>(null);
  const [contract, setContract] = useState<AdaptiveContract | null>(null);
  const [llmRubric, setLlmRubric] = useState<LlmRubricSummary | null>(null);

  const busy = runningTests || submitting;

  const handleRunTests = useCallback(async () => {
    setRunningTests(true);
    setError(null);
    setTestResult(null);
    try {
      const submission = await createCodeSubmission({
        challenge_id: challenge.id,
        session_id: sessionId,
        submitted_code: code,
      });
      setTestResult(submission);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test run failed");
    } finally {
      setRunningTests(false);
    }
  }, [challenge.id, code, sessionId]);

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    setContract(null);
    setLlmRubric(null);
    setSubmitResult(null);
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
      setSubmitResult(submission);
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
      setSubmitting(false);
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
          Question {questionIndex + 1} · {difficulty} · {challenge.language}
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

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleRunTests}
          disabled={busy || disabled || !code.trim()}
          className="rounded-lg border border-border bg-white px-4 py-2 text-sm font-semibold text-neutral transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
        >
          {runningTests ? "Running tests…" : "Run tests"}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy || disabled || !code.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Submit answer"}
        </button>
        {error && (
          <p className="text-sm text-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <p className="text-xs text-neutral/50">
        Run tests executes the E2B sandbox only (practice, no LLM grading). Submit
        answer records your response and runs the full adaptive loop.
      </p>

      {testResult && (
        <SandboxResultsPanel
          result={testResult}
          title="Practice run"
          subtitle="Sandbox only — not counted toward your adaptive session."
        />
      )}

      {submitResult && (
        <SandboxResultsPanel
          result={submitResult}
          title="Submitted answer"
          subtitle="Sandbox score for your official submission."
        />
      )}

      {llmRubric && <LlmRubricPanel rubric={llmRubric} />}

      {contract && <ContractPanel contract={contract} />}
    </div>
  );
}
