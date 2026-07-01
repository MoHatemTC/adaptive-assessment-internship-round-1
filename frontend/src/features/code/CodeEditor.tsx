"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  CodeConsolePanel,
  submissionToConsoleLines,
  type ConsoleLine,
} from "@/features/code/CodeConsolePanel";
import {
  createAdaptiveCodeSubmission,
  createCodeSubmissionAndWait,
  type AdaptiveContract,
  type ChallengeRead,
  type DifficultyLevel,
} from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[280px] items-center justify-center text-sm text-gray-400">
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
  onSubmitted?: (result: { contract: AdaptiveContract }) => void;
  /** Called once on mount so parent can trigger submit when the timer expires. */
  registerAutoSubmit?: (submit: () => void) => void;
}

export function CodeEditor({
  challenge,
  sessionId,
  assessmentId,
  questionIndex,
  difficulty,
  disabled = false,
  onSubmitted,
  registerAutoSubmit,
}: CodeEditorProps) {
  const [code, setCode] = useState(challenge.starter_code);
  const [runningTests, setRunningTests] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consoleLines, setConsoleLines] = useState<ConsoleLine[]>([
    {
      id: "ready",
      tone: "info",
      text: "Ready. Click 'Run Code' to execute.",
    },
  ]);
  const editorShellRef = useRef<HTMLDivElement>(null);
  const [editorHeight, setEditorHeight] = useState(360);

  useLayoutEffect(() => {
    const node = editorShellRef.current;
    if (!node) return;

    const updateHeight = () => {
      setEditorHeight(Math.max(280, node.clientHeight));
    };

    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const busy = runningTests || submitting;

  const handleReset = useCallback(() => {
    setCode(challenge.starter_code);
    setConsoleLines([
      {
        id: "reset",
        tone: "muted",
        text: "Editor reset to starter code.",
      },
    ]);
    setError(null);
  }, [challenge.starter_code]);

  const handleRunTests = useCallback(async () => {
    setRunningTests(true);
    setError(null);
    setConsoleLines([
      { id: "running", tone: "info", text: "Running sandbox tests…" },
    ]);
    try {
      const submission = await createCodeSubmissionAndWait({
        challenge_id: challenge.id,
        session_id: sessionId,
        submitted_code: code,
      });
      setConsoleLines(submissionToConsoleLines(submission));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Test run failed";
      setError(message);
      setConsoleLines([{ id: "run-error", tone: "error", text: message }]);
    } finally {
      setRunningTests(false);
    }
  }, [challenge.id, code, sessionId]);

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const adaptive = await createAdaptiveCodeSubmission({
        challenge_id: challenge.id,
        session_id: sessionId,
        assessment_id: assessmentId,
        submitted_code: code,
        question_index: questionIndex,
        difficulty,
      });
      setConsoleLines([
        {
          id: "submitted",
          tone: "success",
          text: "Solution submitted. Preparing next step…",
        },
      ]);
      onSubmitted?.({ contract: adaptive.contract });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Submission failed";
      setError(message);
      setConsoleLines([{ id: "submit-error", tone: "error", text: message }]);
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

  useEffect(() => {
    registerAutoSubmit?.(() => {
      void handleSubmit();
    });
  }, [handleSubmit, registerAutoSubmit]);

  return (
    <section className="flex min-h-[420px] w-full flex-[1.5] flex-col gap-sm lg:sticky lg:top-[88px] lg:h-[calc(100vh-140px)]">
      <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-editor-border bg-editor-bg shadow-editor">
        <div className="flex items-center justify-between border-b border-editor-border bg-editor-header px-sm py-2">
          <span className="flex items-center gap-1 rounded-full bg-editor-chip px-3 py-1 text-label-sm capitalize text-gray-300">
            {challenge.language}
          </span>
          <div className="flex items-center gap-xs text-gray-400">
            <button
              type="button"
              onClick={handleReset}
              aria-label="Reset Code"
              className="rounded p-1 transition hover:bg-editor-chip hover:text-white"
            >
              <span className="material-symbols-outlined text-[18px]">refresh</span>
            </button>
          </div>
        </div>
        <div ref={editorShellRef} className="min-h-[280px] flex-1">
          <MonacoEditor
            height={editorHeight}
            language={challenge.language}
            theme="vs-dark"
            value={code}
            onChange={(value) => setCode(value ?? "")}
            options={{
              readOnly: disabled,
              minimap: { enabled: false },
              fontSize: 14,
              lineHeight: 22,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              padding: { top: 12 },
              tabSize: 2,
              wordWrap: "on",
            }}
          />
        </div>
      </div>

      <CodeConsolePanel
        lines={consoleLines}
        onClear={() =>
          setConsoleLines([
            {
              id: "cleared",
              tone: "muted",
              text: "Console cleared.",
            },
          ])
        }
      />

      <div className="mt-xs flex items-center justify-end gap-sm">
        <button
          type="button"
          onClick={handleRunTests}
          disabled={busy || disabled || !code.trim()}
          className="flex h-[44px] items-center justify-center gap-2 rounded-lg border border-outline px-xl text-label-md text-on-surface transition hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[20px]">play_arrow</span>
          {runningTests ? "Running…" : "Run Code"}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy || disabled || !code.trim()}
          className="flex h-[44px] items-center justify-center gap-2 rounded-lg bg-primary px-xl text-label-md text-on-primary shadow-sm transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Submit Solution"}
          <span className="material-symbols-outlined text-[20px]">send</span>
        </button>
      </div>

      {error && (
        <p className="text-body-sm text-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
