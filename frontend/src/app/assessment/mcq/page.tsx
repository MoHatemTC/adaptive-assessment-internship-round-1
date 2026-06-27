"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import McqCard, { McqOption } from "@/features/mcq/McqCard";
import { PlatformSessionProctoring } from "@/features/proctoring/PlatformSessionProctoring";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const TOTAL_QUESTIONS = 5;

interface McqQuestion {
  id: number;
  question_text: string;
  options: McqOption[];
  difficulty?: string;
  dimension?: string | null;
}

interface AnswerResponse {
  next_question: McqQuestion | null;
  is_complete: boolean;
}

export default function McqAssessmentPage() {
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  const [currentQuestion, setCurrentQuestion] = useState<McqQuestion | null>(
    null
  );
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // Seed the first question. Subsequent questions are returned adaptively by
  // the /answer endpoint.
  useEffect(() => {
    async function createInitialQuestion() {
      try {
        setErrorMessage("");

        const response = await fetch(`${API_BASE}/mcq/questions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question_text:
              "A learner is solving a technical assessment question. What is the best first step before choosing an answer?",
            difficulty: "easy",
            correct_option: "A",
            options: [
              {
                label: "A",
                text: "Read the question carefully and identify the main requirement",
              },
              {
                label: "B",
                text: "Choose an answer quickly without analyzing the question",
              },
              { label: "C", text: "Skip the question immediately without trying" },
              {
                label: "D",
                text: "Select the longest option because it looks more detailed",
              },
            ],
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to create the initial MCQ question");
        }

        const data: McqQuestion = await response.json();
        setCurrentQuestion(data);
        setQuestionIndex(0);
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Something went wrong while loading the MCQ"
        );
      }
    }

    createInitialQuestion();
  }, []);

  const handleSubmit = useCallback(
    async (questionId: number, selectedLabel: string) => {
      try {
        setIsSubmitting(true);
        setErrorMessage("");

        const response = await fetch(
          `${API_BASE}/mcq/sessions/${sessionId}/answer`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              question_id: questionId,
              selected_option: selectedLabel,
              question_index: questionIndex,
              total_questions: TOTAL_QUESTIONS,
            }),
          }
        );

        if (!response.ok) {
          throw new Error("Failed to submit the MCQ answer");
        }

        const data: AnswerResponse = await response.json();

        if (data.is_complete || !data.next_question) {
          setIsComplete(true);
          setCurrentQuestion(null);
          return;
        }

        setCurrentQuestion(data.next_question);
        setQuestionIndex((previous) => previous + 1);
      } catch (error) {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Something went wrong while submitting the answer"
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [questionIndex, sessionId]
  );

  return (
    <PlatformSessionProctoring>
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#FBFBFD] p-6 font-[family-name:var(--font-jakarta)]">
      <div className="mb-6 w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-[#1F2430]">
          Adaptive MCQ Assessment
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
            Thank you for completing the MCQ assessment.
          </p>
        </div>
      )}

      {!isComplete && !currentQuestion && !errorMessage && (
        <p className="text-sm text-[#606575]">Loading MCQ...</p>
      )}

      {!isComplete && currentQuestion && (
        <>
          <div className="mb-4 w-full max-w-2xl rounded-xl border border-[#D8DDF0] bg-white p-4 text-sm text-[#343434]">
            <span className="font-semibold">Question:</span>{" "}
            {questionIndex + 1} / {TOTAL_QUESTIONS}
          </div>

          <McqCard
            key={currentQuestion.id}
            questionId={currentQuestion.id}
            questionText={currentQuestion.question_text}
            options={currentQuestion.options}
            onSubmit={handleSubmit}
            isSubmitting={isSubmitting}
          />
        </>
      )}
    </main>
    </PlatformSessionProctoring>
  );
}
