"use client";

import { useEffect, useMemo, useState } from "react";
import McqCard from "@/features/mcq/McqCard";

interface McqOption {
  label: string;
  text: string;
}

interface McqQuestion {
  id: number;
  question_text: string;
  options: McqOption[];
  difficulty: "beginner" | "intermediate" | "advanced";
  dimension: "Thinking" | "Soft" | "Work" | "Digital/AI" | "Growth" | null;
}

const API_BASE_URL = "/api";

export default function McqAssessmentPage() {
  const sessionId = useMemo(() => crypto.randomUUID(), []);

  const [currentQuestion, setCurrentQuestion] = useState<McqQuestion | null>(
    null
  );
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [latestAdaptiveSummary, setLatestAdaptiveSummary] = useState("");

  useEffect(() => {
    async function createInitialQuestion() {
      try {
        setErrorMessage("");

        const response = await fetch(`${API_BASE_URL}/mcq/questions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question_text:
              "A learner is solving a technical assessment question. What is the best first step before choosing an answer?",
            difficulty: "beginner",
            dimension: "Thinking",
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
              {
                label: "C",
                text: "Skip the question immediately without trying",
              },
              {
                label: "D",
                text: "Select the longest option because it looks more detailed",
              },
            ],
          }),
        });

        if (!response.ok) {
          throw new Error("Failed to create initial MCQ question");
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

  const handleSubmit = async (
    questionId: string,
    selectedOptionId: string
  ) => {
    try {
      setIsSubmitting(true);
      setErrorMessage("");

      const response = await fetch(`${API_BASE_URL}/mcq/adaptive-submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question_id: Number(questionId),
          session_id: sessionId,
          question_index: questionIndex,
          selected_option: selectedOptionId,
          learner_profile: {
            level: "beginner",
            target_role: "software engineering intern",
            assessment_goal:
              "Evaluate problem solving, workplace readiness, digital AI literacy, and growth mindset",
          },
          admin_config: {
            allowed_skills: [
              "Thinking",
              "Soft",
              "Work",
              "Digital/AI",
              "Growth",
            ],
            allowed_topics: [
              "problem_solving",
              "communication",
              "work_readiness",
              "digital_ai_literacy",
              "learning_growth",
            ],
            max_difficulty: "advanced",
          },
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit MCQ answer");
      }

      const data = await response.json();

      setCurrentQuestion(data.next_question);
      setQuestionIndex((previousIndex) => previousIndex + 1);

      const nextPlan = data.next_plan;
      setLatestAdaptiveSummary(
        `Next item adapted to ${nextPlan.next_dimension ?? nextPlan.next_skill} at ${nextPlan.next_difficulty} level.`
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Something went wrong while submitting the answer"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#F4F6FB] p-6">
      <div className="mb-6 w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-[#1F2430]">
          Adaptive MCQ Assessment
        </h1>

        <p className="mt-2 text-sm text-[#606575]">
          Each answer is graded silently. The next question is adapted using
          learner evidence, admin configuration, and LLM generation.
        </p>

        <p className="mt-2 text-xs text-[#606575]">
          Session: {sessionId}
        </p>
      </div>

      {errorMessage && (
        <div className="mb-4 w-full max-w-2xl rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      {!currentQuestion && !errorMessage && (
        <p className="text-sm text-[#606575]">Loading MCQ...</p>
      )}

      {currentQuestion && (
        <>
          <div className="mb-4 w-full max-w-2xl rounded-xl border border-[#D8DDF0] bg-white p-4 text-sm text-[#343434]">
            <p>
              <span className="font-semibold">Question:</span>{" "}
              {questionIndex + 1}
            </p>
            <p>
              <span className="font-semibold">Difficulty:</span>{" "}
              {currentQuestion.difficulty}
            </p>
            <p>
              <span className="font-semibold">Dimension:</span>{" "}
              {currentQuestion.dimension ?? "Thinking"}
            </p>
          </div>

          <McqCard
            questionId={String(currentQuestion.id)}
            questionText={currentQuestion.question_text}
            options={currentQuestion.options}
            onSubmit={handleSubmit}
            isSubmitting={isSubmitting}
          />
        </>
      )}

      {latestAdaptiveSummary && (
        <div className="mt-6 w-full max-w-2xl rounded-xl border border-[#D8DDF0] bg-white p-4 text-sm text-[#343434]">
          {latestAdaptiveSummary}
        </div>
      )}
    </main>
  );
}
