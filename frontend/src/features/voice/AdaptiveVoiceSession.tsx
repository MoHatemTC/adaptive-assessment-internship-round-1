"use client";

import { useCallback, useEffect, useState } from "react";

import VoiceRecorder from "@/features/voice/VoiceRecorder";
import {
  type Difficulty,
  type FollowUpDepth,
  processVoiceSession,
  startAdaptiveVoiceSession,
} from "@/lib/voice-api";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/** Derive a WebSocket base URL from the HTTP API base. */
function getWsBase(): string {
  return API_BASE.replace(/^https/, "wss").replace(/^http/, "ws");
}

type Phase =
  | "initializing"
  | "recording"
  | "processing"
  | "transitioning"
  | "complete"
  | "error";

/** Three pulsing dots over a status label — used for non-recording phases. */
function ThreeDots({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center">
      <div className="flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          style={{
            backgroundColor: "#004EFF",
            animation: "dotPulse 900ms ease-in-out infinite",
            animationDelay: "0ms",
          }}
        />
        <span
          className="w-2 h-2 rounded-full"
          style={{
            backgroundColor: "#004EFF",
            animation: "dotPulse 900ms ease-in-out infinite",
            animationDelay: "150ms",
          }}
        />
        <span
          className="w-2 h-2 rounded-full"
          style={{
            backgroundColor: "#004EFF",
            animation: "dotPulse 900ms ease-in-out infinite",
            animationDelay: "300ms",
          }}
        />
      </div>
      <p
        role="status"
        aria-live="polite"
        className="text-sm font-normal mt-3"
        style={{ color: "#343434" }}
      >
        {label}
      </p>
    </div>
  );
}

/** Soft bordered container that echoes the design's state cards. */
function StatusCard({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="w-full max-w-xs rounded-2xl border bg-white shadow-sm px-6 py-7 flex flex-col items-center text-center card-enter"
      style={{ borderColor: "#D8DDF0" }}
    >
      {children}
    </div>
  );
}

export interface AdaptiveVoiceSessionProps {
  sessionId: string;
  initialQuestion: string;
  initialDifficulty: Difficulty;
  timeLimitSeconds?: number;
  learnerProfile: Record<string, unknown>;
  adminConfig: Record<string, unknown>;
  onComplete?: () => void;
}

export default function AdaptiveVoiceSession({
  sessionId,
  initialQuestion,
  initialDifficulty,
  timeLimitSeconds = 120,
  learnerProfile,
  adminConfig,
  onComplete,
}: AdaptiveVoiceSessionProps) {
  const [phase, setPhase] = useState<Phase>("initializing");
  const [currentQuestion, setCurrentQuestion] = useState(initialQuestion);
  const [currentDifficulty, setCurrentDifficulty] =
    useState<Difficulty>(initialDifficulty);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [voiceSessionId, setVoiceSessionId] = useState<number | null>(null);
  const [followUpDepth, setFollowUpDepth] = useState<FollowUpDepth>("simple");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const maxQuestions =
    typeof adminConfig.max_questions === "number"
      ? adminConfig.max_questions
      : typeof adminConfig.question_count === "number"
        ? adminConfig.question_count
        : 10;

  const initSession = useCallback(
    async (question: string, difficulty: Difficulty, qIndex: number) => {
      try {
        const resp = await startAdaptiveVoiceSession({
          session_id: sessionId,
          question_text: question,
          question_index: qIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: difficulty,
          learner_profile: learnerProfile,
          admin_config: adminConfig,
        });
        setVoiceSessionId(resp.voice_session_id);
        setPhase("recording");
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to start session.",
        );
        setPhase("error");
      }
    },
    [sessionId, timeLimitSeconds, learnerProfile, adminConfig],
  );

  // Initialize on mount.
  useEffect(() => {
    void initSession(initialQuestion, initialDifficulty, 0);
    // Only run on mount — deps are stable props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRecordingComplete = useCallback(
    async (_transcript: string) => {
      if (voiceSessionId === null) return;
      setPhase("processing");

      try {
        const result = await processVoiceSession(voiceSessionId, {
          session_id: sessionId,
          question_text: currentQuestion,
          question_index: questionIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: currentDifficulty,
          learner_profile: learnerProfile,
          admin_config: adminConfig,
          voice_session_id: voiceSessionId,
        });

        const contract = result.adaptive_contract;

        if (!contract || contract.stop || questionIndex >= maxQuestions - 1) {
          setPhase("complete");
          onComplete?.();
          return;
        }

        const nextQuestion = contract.next_question_text;
        const nextDifficulty = contract.difficulty;
        const nextDepth = contract.follow_up_depth;
        const nextIndex = questionIndex + 1;

        setCurrentQuestion(nextQuestion);
        setCurrentDifficulty(nextDifficulty);
        setFollowUpDepth(nextDepth);
        setQuestionIndex(nextIndex);
        setPhase("transitioning");

        const resp = await startAdaptiveVoiceSession({
          session_id: sessionId,
          question_text: nextQuestion,
          question_index: nextIndex,
          time_limit_seconds: timeLimitSeconds,
          target_difficulty: nextDifficulty,
          learner_profile: learnerProfile,
          admin_config: adminConfig,
        });
        setVoiceSessionId(resp.voice_session_id);

        setTimeout(() => {
          setPhase("recording");
        }, 600);
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Processing failed.",
        );
        setPhase("error");
      }
    },
    [
      voiceSessionId,
      sessionId,
      currentQuestion,
      currentDifficulty,
      questionIndex,
      timeLimitSeconds,
      learnerProfile,
      adminConfig,
      maxQuestions,
      onComplete,
    ],
  );

  const handleRetry = () => {
    setPhase("initializing");
    setErrorMessage(null);
    setVoiceSessionId(null);
    setQuestionIndex(0);
    setCurrentQuestion(initialQuestion);
    setCurrentDifficulty(initialDifficulty);
    setFollowUpDepth("simple");
    void initSession(initialQuestion, initialDifficulty, 0);
  };

  const wsUrl = `${getWsBase()}/voice/sessions`;
  const progressPct = ((questionIndex + 1) / maxQuestions) * 100;

  return (
    <>
      <style>{`
        @keyframes dotPulse {
          0%, 100% { opacity: 0.2; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1);   }
        }
        @keyframes cardEntrance {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0);   }
        }
        .card-enter {
          animation: cardEntrance 300ms ease-out forwards;
        }
      `}</style>

      <div
        className="min-h-screen font-[family-name:var(--font-jakarta)]"
        style={{ backgroundColor: "#FBFBFD" }}
      >
        {/* Thin progress bar — fixed to very top of viewport */}
        <div
          className="fixed top-0 left-0 right-0 h-[3px] z-20"
          style={{ backgroundColor: "#E6EEFF" }}
        >
          <div
            className="h-full transition-all duration-500 ease-out"
            style={{ width: `${progressPct}%`, backgroundColor: "#004EFF" }}
          />
        </div>

        {/* Top chrome — brand wordmark + utility icons */}
        <header className="flex items-center justify-between px-6 pt-5 pb-2">
          <span
            className="text-base font-bold tracking-tight"
            style={{ color: "#004EFF" }}
          >
            Masaar
          </span>
          <div className="flex items-center gap-3" style={{ color: "#343434" }}>
            <button
              type="button"
              aria-label="Help"
              className="transition-colors duration-150 cursor-pointer"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width={20}
                height={20}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="w-5 h-5"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M9.6 9a2.4 2.4 0 0 1 4.5 1.1c0 1.6-2.1 2-2.1 3.4" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </button>
            <button
              type="button"
              aria-label="Settings"
              className="transition-colors duration-150 cursor-pointer"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width={20}
                height={20}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="w-5 h-5"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
          </div>
        </header>

        {/* Single-column centered content */}
        <div className="max-w-2xl mx-auto pt-6 pb-20 px-6">
          {/* Centered title */}
          <div className="text-center mb-6">
            <h1
              className="text-base font-semibold tracking-tight"
              style={{ color: "#1F2430" }}
            >
              Voice Assessment
            </h1>
            <p
              className="text-sm font-normal mt-1"
              style={{ color: "#343434" }}
            >
              Question {questionIndex + 1}
            </p>
          </div>

          {/* Question card — key remounts on each new question, retriggering entrance animation */}
          <div
            key={questionIndex}
            className="bg-white rounded-2xl border shadow-sm px-8 py-7 card-enter"
            style={{ borderColor: "#D8DDF0" }}
          >
            <p
              className="text-lg font-medium leading-relaxed"
              style={{ color: "#1F2430" }}
            >
              {`"${currentQuestion}"`}
            </p>
          </div>

          {/* Phase-specific UI */}
          <div className="mt-10 flex flex-col items-center">
            {phase === "initializing" && (
              <StatusCard>
                <ThreeDots label="Preparing your question…" />
              </StatusCard>
            )}

            {phase === "recording" && voiceSessionId !== null && (
              <div className="w-full flex flex-col items-center">
                <VoiceRecorder
                  voiceSessionId={String(voiceSessionId)}
                  timeLimitSeconds={timeLimitSeconds}
                  onComplete={handleRecordingComplete}
                  wsUrl={wsUrl}
                />
                <p
                  className="text-sm text-center mt-4"
                  style={{ color: "#343434" }}
                >
                  Speak clearly. Recording stops automatically.
                </p>
              </div>
            )}

            {phase === "processing" && (
              <StatusCard>
                <ThreeDots label="Analyzing your response…" />
              </StatusCard>
            )}

            {phase === "transitioning" && (
              <StatusCard>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width={24}
                  height={24}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#004EFF"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="w-6 h-6"
                  aria-hidden="true"
                >
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
                <p
                  className="text-base font-semibold mt-3"
                  style={{ color: "#1F2430" }}
                >
                  Question {questionIndex + 1}
                </p>
                <p
                  role="status"
                  aria-live="polite"
                  className="text-sm mt-1"
                  style={{ color: "#343434" }}
                >
                  Loading next…
                </p>
              </StatusCard>
            )}

            {phase === "complete" && (
              <div className="flex flex-col items-center card-enter">
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: "#E1F5EE" }}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width={32}
                    height={32}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="#14B86A"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="w-8 h-8"
                    aria-hidden="true"
                  >
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <p
                  className="text-xl font-semibold mt-6"
                  style={{ color: "#1F2430" }}
                >
                  Assessment Complete
                </p>
                <p className="text-sm mt-2" style={{ color: "#343434" }}>
                  Thank you for completing the assessment.
                </p>
              </div>
            )}

            {phase === "error" && (
              <div
                className="bg-white rounded-2xl border shadow-sm p-8 w-full flex flex-col items-center"
                style={{ borderColor: "#D8DDF0" }}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width={32}
                  height={32}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#E5484D"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="w-8 h-8"
                  aria-hidden="true"
                >
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <p className="text-sm mt-2" style={{ color: "#E5484D" }}>
                  {errorMessage ?? "An unexpected error occurred."}
                </p>
                <button
                  type="button"
                  onClick={handleRetry}
                  aria-label="Retry assessment"
                  className="text-white text-sm font-medium rounded-xl px-6 py-3 mt-4 transition-colors duration-150 cursor-pointer min-h-[44px]"
                  style={{ backgroundColor: "#004EFF" }}
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
