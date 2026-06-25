"use client";

import { useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

interface DiagramNextQuestion {
  id: number;
  svg_content: string;
  prompt: string;
  difficulty: string;
  dimension?: string | null;
}

interface DiagramToolProps {
  questionId: number;
  svgContent: string;
  prompt: string;
  questionIndex: number;
  totalQuestions: number;
  sessionId: string;
  onComplete: () => void;
  onNext: (nextQuestion: DiagramNextQuestion) => void;
}

export default function DiagramTool({
  questionId,
  svgContent,
  prompt,
  questionIndex,
  totalQuestions,
  sessionId,
  onComplete,
  onNext,
}: DiagramToolProps) {
  const [phase, setPhase] = useState<"diagram" | "question" | "submitting">(
    "diagram"
  );
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!answer.trim() || phase === "submitting") return;
    setPhase("submitting");
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/diagram/sessions/${sessionId}/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_id: questionId,
          answer_text: answer.trim(),
          question_index: questionIndex,
          total_questions: totalQuestions,
        }),
      });
      if (!res.ok) throw new Error("Failed to submit answer");
      const data: {
        next_question: DiagramNextQuestion | null;
        is_complete: boolean;
      } = await res.json();

      if (data.is_complete || !data.next_question) {
        onComplete();
      } else {
        onNext(data.next_question);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setPhase("question");
    }
  };

  if (phase === "diagram") {
    return (
      <section className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <span className="inline-flex rounded-full bg-[#CCE0FF] px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-[#004EFF]">
            Diagram
          </span>
          <span className="text-xs text-[#A0A8B8]">
            Question {questionIndex + 1} / {totalQuestions}
          </span>
        </div>

        <h2 className="mb-4 text-[18px] font-semibold text-[#1F2430]">
          Study the diagram below. One component is missing its label.
        </h2>

        <div
          className="overflow-x-auto rounded-2xl border border-[#D8DDF0] bg-white p-4"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />

        <div className="mt-3 flex items-center gap-2 text-xs text-[#606575]">
          <span
            className="inline-block h-3 w-6 rounded-sm border-2 border-dashed"
            style={{ borderColor: "#FFB300", backgroundColor: "#FFB30022" }}
          />
          <span>The highlighted node with [?] is the one you need to identify.</span>
        </div>

        <button
          type="button"
          onClick={() => setPhase("question")}
          className="mt-6 flex h-[43px] w-full items-center justify-center gap-2 rounded-lg bg-[#004EFF] text-sm font-semibold text-white transition hover:bg-[#3374FF]"
        >
          View Question →
        </button>
      </section>
    );
  }

  return (
    <section className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 shadow-sm">
      <div
        className="mb-4 overflow-hidden rounded-xl border border-[#D8DDF0] bg-white"
        style={{ maxHeight: 180, overflow: "hidden" }}
      >
        <div
          className="pointer-events-none scale-[0.6] origin-top-left"
          style={{ width: "167%" }}
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      </div>

      <h2 className="mb-4 text-[18px] font-semibold text-[#1F2430]">
        {prompt}
      </h2>

      <input
        type="text"
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && answer.trim()) handleSubmit();
        }}
        placeholder="Type the name of the missing component…"
        disabled={phase === "submitting"}
        className="w-full rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 text-sm text-[#1F2430] placeholder-[#A0A8B8] outline-none transition focus:border-[#004EFF] focus:ring-2 focus:ring-[#004EFF]/10 disabled:opacity-60"
      />

      {error && <p className="mt-2 text-xs font-medium text-[#E5484D]">{error}</p>}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={phase === "submitting" || !answer.trim()}
        className="mt-4 flex h-[43px] w-full items-center justify-center gap-2 rounded-lg bg-[#004EFF] text-sm font-semibold text-white transition hover:bg-[#3374FF] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {phase === "submitting" ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Submitting…
          </>
        ) : (
          "Submit Answer"
        )}
      </button>
    </section>
  );
}

export type { DiagramNextQuestion };
