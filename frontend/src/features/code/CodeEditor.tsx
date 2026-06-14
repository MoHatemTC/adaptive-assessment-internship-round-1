"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type { editor as MonacoEditorType } from "monaco-editor";

import { useProctoringStore } from "@/store/proctoringStore";

import { CountdownTimer } from "@/features/code/CountdownTimer";
import { RunResults } from "@/features/code/RunResults";
import { SubmissionResults } from "@/features/code/SubmissionResults";
import {
  createCodeSubmission,
  runCode,
  submitAdaptiveTurn,
  type AdaptiveSubmitResponse,
  type ChallengeRead,
  type RunRead,
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
  remainingSeconds?: number;
  disabled?: boolean;
  adaptiveMode?: boolean;
  /** When adaptiveMode: `api` calls /adaptive/submit; `agent` defers grading to the examiner WS loop. */
  adaptiveGrading?: "api" | "agent";
  onSubmitted?: (result: SubmissionRead) => void;
  onAdaptiveSubmitted?: (result: AdaptiveSubmitResponse) => void;
  onSubmitCode?: (code: string) => void;
  onRunComplete?: () => void;
  onTimerExpire?: () => void;
  blockClipboard?: boolean;
}

export function CodeEditor({
  challenge,
  sessionId,
  remainingSeconds,
  disabled = false,
  adaptiveMode = false,
  adaptiveGrading = "api",
  onSubmitted,
  onAdaptiveSubmitted,
  onSubmitCode,
  onRunComplete,
  onTimerExpire,
  blockClipboard = false,
}: CodeEditorProps) {
  const [code, setCode] = useState(challenge.starter_code);
  const [running, setRunning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<RunRead | null>(null);
  const [submitResult, setSubmitResult] = useState<SubmissionRead | null>(null);
  const [adaptiveMessage, setAdaptiveMessage] = useState<string | null>(null);

  const handleRun = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await runCode({
        session_id: sessionId,
        challenge_id: challenge.id,
        submitted_code: code,
      });
      setRunResult(result);
      onRunComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }, [challenge.id, code, onRunComplete, sessionId]);

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    setAdaptiveMessage(null);
    try {
      if (adaptiveMode) {
        if (adaptiveGrading === "agent") {
          setAdaptiveMessage("Submitted — examiner is evaluating…");
          onSubmitCode?.(code);
        } else {
          const response = await submitAdaptiveTurn(sessionId, {
            challenge_id: challenge.id,
            submitted_code: code,
          });
          setAdaptiveMessage(response.message);
          onAdaptiveSubmitted?.(response);
        }
      } else {
        const submission = await createCodeSubmission({
          challenge_id: challenge.id,
          session_id: sessionId,
          submitted_code: code,
        });
        setSubmitResult(submission);
        onSubmitted?.(submission);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }, [adaptiveGrading, adaptiveMode, challenge.id, code, onAdaptiveSubmitted, onSubmitCode, onSubmitted, sessionId]);

  const busy = running || submitting;
  const locked = disabled || (remainingSeconds !== undefined && remainingSeconds <= 0);

  const handleEditorMount = useCallback(
    (editor: MonacoEditorType.IStandaloneCodeEditor, monaco: typeof import("monaco-editor")) => {
      if (!blockClipboard) return;
      const queueEvent = useProctoringStore.getState().queueEvent;
      const setWarning = useProctoringStore.getState().setWarning;
      const recordBlocked = (
        eventType: "copy_blocked" | "paste_blocked" | "keyboard_shortcut",
        metadata?: Record<string, string>,
      ) => {
        queueEvent({
          event_type: eventType,
          client_timestamp: new Date().toISOString(),
          metadata,
        });
        if (eventType === "paste_blocked") {
          setWarning("Paste is disabled during the assessment.");
        } else {
          setWarning("Copy and cut are disabled during the assessment.");
        }
      };

      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyC, () => {
        recordBlocked("keyboard_shortcut", { key: "Ctrl+C" });
        recordBlocked("copy_blocked", { action: "copy" });
      });
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyX, () => {
        recordBlocked("keyboard_shortcut", { key: "Ctrl+X" });
        recordBlocked("copy_blocked", { action: "cut" });
      });
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyV, () => {
        recordBlocked("keyboard_shortcut", { key: "Ctrl+V" });
        recordBlocked("paste_blocked");
      });

      const dom = editor.getContainerDomNode();
      const stopClipboard = (event: ClipboardEvent, type: "copy_blocked" | "paste_blocked") => {
        event.preventDefault();
        event.stopPropagation();
        recordBlocked(type);
      };
      dom.addEventListener("copy", (e) => stopClipboard(e, "copy_blocked"), true);
      dom.addEventListener("cut", (e) => stopClipboard(e, "copy_blocked"), true);
      dom.addEventListener("paste", (e) => stopClipboard(e, "paste_blocked"), true);
    },
    [blockClipboard],
  );

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-neutral">{challenge.title}</h2>
          <p className="mt-1 text-sm text-neutral/80">{challenge.description}</p>
        </div>
        {remainingSeconds !== undefined && (
          <CountdownTimer
            remainingSeconds={remainingSeconds}
            label="Challenge time"
            onExpire={onTimerExpire}
          />
        )}
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <MonacoEditor
          height="320px"
          language={challenge.language}
          theme="vs-light"
          value={code}
          onChange={(value) => setCode(value ?? "")}
          onMount={handleEditorMount}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            scrollBeyondLastLine: false,
            automaticLayout: true,
            readOnly: locked,
          }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={handleRun}
          disabled={busy || locked || !code.trim()}
          className="rounded-lg border border-primary px-4 py-2 text-sm font-semibold text-primary transition hover:bg-primary-20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Running…" : "Run (visible tests)"}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={busy || locked || !code.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Submitting…" : "Submit for grading"}
        </button>
        {error && (
          <p className="text-sm text-error" role="alert">
            {error}
          </p>
        )}
      </div>

      {runResult && <RunResults result={runResult} />}
      {adaptiveMode && adaptiveMessage && (
        <p className="rounded-lg border border-border bg-surface-muted px-4 py-3 text-sm text-neutral">
          {adaptiveMessage}
        </p>
      )}
      {!adaptiveMode && submitResult && <SubmissionResults result={submitResult} />}
    </div>
  );
}
