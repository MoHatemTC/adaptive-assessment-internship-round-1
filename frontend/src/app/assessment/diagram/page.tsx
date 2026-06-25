"use client";

import { useEffect, useMemo, useState } from "react";

import DiagramTool, { DiagramNextQuestion } from "@/features/diagram/DiagramTool";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

const TOTAL_QUESTIONS = 5;

interface DiagramQuestion {
  id: number;
  svg_content: string;
  prompt: string;
  difficulty?: string;
  dimension?: string | null;
}

const SEED_SVG = `<svg width="600" height="400" viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Three-tier web architecture diagram">
  <rect x="30" y="155" width="110" height="60" rx="10" fill="#E6EEFF" stroke="#004EFF" stroke-width="2" />
  <text x="85" y="190" text-anchor="middle" font-family="Arial" font-size="14" fill="#1F2430">Users</text>
  <line x1="140" y1="185" x2="205" y2="185" stroke="#606575" stroke-width="2" marker-end="url(#arrow)" />
  <rect x="205" y="155" width="130" height="60" rx="10" fill="#FFB300" stroke="#B97800" stroke-width="2" stroke-dasharray="6,3" />
  <text x="270" y="190" text-anchor="middle" font-family="Arial" font-size="16" font-weight="bold" fill="#1F2430">[?]</text>
  <line x1="335" y1="185" x2="395" y2="125" stroke="#606575" stroke-width="2" marker-end="url(#arrow)" />
  <line x1="335" y1="185" x2="395" y2="245" stroke="#606575" stroke-width="2" marker-end="url(#arrow)" />
  <rect x="395" y="95" width="145" height="55" rx="10" fill="#FBFBFD" stroke="#D8DDF0" stroke-width="2" />
  <text x="467" y="128" text-anchor="middle" font-family="Arial" font-size="14" fill="#1F2430">Web Server A</text>
  <rect x="395" y="215" width="145" height="55" rx="10" fill="#FBFBFD" stroke="#D8DDF0" stroke-width="2" />
  <text x="467" y="248" text-anchor="middle" font-family="Arial" font-size="14" fill="#1F2430">Web Server B</text>
  <line x1="467" y1="150" x2="467" y2="215" stroke="#606575" stroke-width="2" marker-end="url(#arrow)" />
  <rect x="395" y="310" width="145" height="55" rx="10" fill="#EAF7EF" stroke="#2F9E44" stroke-width="2" />
  <text x="467" y="342" text-anchor="middle" font-family="Arial" font-size="14" fill="#1F2430">Database</text>
  <line x1="467" y1="270" x2="467" y2="310" stroke="#606575" stroke-width="2" marker-end="url(#arrow)" />
  <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#606575" /></marker></defs>
</svg>`;

export default function DiagramAssessmentPage() {
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  const [currentQuestion, setCurrentQuestion] = useState<DiagramQuestion | null>(
    null
  );
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    async function createInitialQuestion() {
      try {
        setErrorMessage("");

        const response = await fetch(apiUrl("/diagram/questions"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            svg_content: SEED_SVG,
            prompt:
              "What is the blank component [?] in this three-tier web architecture?",
            correct_label: "Load Balancer",
            rubric:
              "Accept: load balancer, LB, reverse proxy. Reject: firewall, CDN, router.",
            difficulty: "easy",
            dimension: "digital_ai",
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to create the initial diagram question");
        }

        const data: DiagramQuestion = await response.json();
        setCurrentQuestion(data);
        setQuestionIndex(0);
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Something went wrong while loading the diagram"
        );
      }
    }

    createInitialQuestion();
  }, []);

  const handleNext = (nextQuestion: DiagramNextQuestion) => {
    setCurrentQuestion(nextQuestion);
    setQuestionIndex((previous) => previous + 1);
  };

  const handleComplete = () => {
    setIsComplete(true);
    setCurrentQuestion(null);
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#FBFBFD] p-6 font-[family-name:var(--font-jakarta)]">
      <div className="mb-6 w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-[#1F2430]">
          Adaptive Diagram Assessment
        </h1>
        <p className="mt-2 text-sm text-[#606575]">
          Each answer is graded silently. The next question adapts to your
          responses.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-4 w-full max-w-2xl rounded-lg border border-[#E5484D] bg-red-50 p-4 text-sm text-[#E5484D]">
          {errorMessage}
        </div>
      )}

      {isComplete && (
        <div className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-white p-6 text-center">
          <p className="text-xl font-semibold text-[#1F2430]">
            Assessment Complete
          </p>
          <p className="mt-2 text-sm text-[#606575]">
            Thank you for completing the diagram assessment.
          </p>
        </div>
      )}

      {!isComplete && !currentQuestion && !errorMessage && (
        <p className="text-sm text-[#606575]">Loading diagram...</p>
      )}

      {!isComplete && currentQuestion && (
        <>
          <div className="mb-4 w-full max-w-2xl rounded-xl border border-[#D8DDF0] bg-white p-4 text-sm text-[#343434]">
            <span className="font-semibold">Question:</span> {questionIndex + 1} / {TOTAL_QUESTIONS}
          </div>

          <DiagramTool
            key={currentQuestion.id}
            questionId={currentQuestion.id}
            svgContent={currentQuestion.svg_content}
            prompt={currentQuestion.prompt}
            questionIndex={questionIndex}
            totalQuestions={TOTAL_QUESTIONS}
            sessionId={sessionId}
            onComplete={handleComplete}
            onNext={handleNext}
          />
        </>
      )}
    </main>
  );
}
