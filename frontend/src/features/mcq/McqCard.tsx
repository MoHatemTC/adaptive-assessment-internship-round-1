"use client";

import { useState } from "react";

type MCQOption = {
  label: string;
  text: string;
};

type McqCardProps = {
  questionId?: number;
  questionText?: string;
  options?: MCQOption[];
};

export default function McqCard({
  questionId = 1,
  questionText = "What is the output of print(2 + 3)?",
  options = [
    { label: "A", text: "2" },
    { label: "B", text: "3" },
    { label: "C", text: "5" },
    { label: "D", text: "23" },
  ],
}: McqCardProps) {
  const [selectedOption, setSelectedOption] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const handleSubmit = async () => {
    if (!selectedOption) {
      setMessage("Please select an answer before submitting.");
      return;
    }

    try {
      setIsSubmitting(true);
      setMessage("");

      const apiBaseUrl =
        process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

      const response = await fetch(`${apiBaseUrl}/mcq/submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question_id: questionId,
          selected_option: selectedOption,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit MCQ answer.");
      }

      const result = await response.json();

      console.log("MCQ submitted:", result);

      // Silent grading: do not reveal correct/wrong answer immediately.
      setMessage("Answer submitted successfully.");
    } catch (error) {
      console.error(error);
      setMessage("Could not submit the answer. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="w-full max-w-2xl rounded-3xl border border-[#D8DDF0] bg-[#FBFBFD] p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <span className="inline-flex rounded-full bg-[#CCE0FF] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-[#004EFF]">
            MCQ Tool
          </span>

          <h2 className="mt-4 text-2xl font-bold leading-tight text-[#1F2430]">
            Multiple Choice Question
          </h2>
        </div>

        <span className="rounded-full border border-[#004EFF40] bg-white px-4 py-2 text-sm font-semibold text-[#004EFF]">
          Q{questionId}
        </span>
      </div>

      <p className="mb-5 text-base leading-6 text-[#343434]">
        {questionText}
      </p>

      <div className="space-y-3">
        {options.map((option) => {
          const isSelected = selectedOption === option.label;

          return (
            <label
              key={option.label}
              className={`flex cursor-pointer items-center gap-3 rounded-2xl border p-4 transition ${
                isSelected
                  ? "border-[#004EFF] bg-[#E6EEFF]"
                  : "border-[#D8DDF0] bg-white hover:border-[#004EFF40]"
              }`}
            >
              <input
                type="radio"
                name={`mcq-${questionId}`}
                value={option.label}
                checked={isSelected}
                onChange={() => setSelectedOption(option.label)}
                className="h-4 w-4 accent-[#004EFF]"
              />

              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#CCE0FF] text-sm font-semibold text-[#004EFF]">
                {option.label}
              </span>

              <span className="text-sm font-medium text-[#1F2430]">
                {option.text}
              </span>
            </label>
          );
        })}
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          className="h-[43px] rounded-lg bg-[#004EFF] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#3374FF] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? "Submitting..." : "Submit Answer"}
        </button>

        {message && (
          <p
            className={`text-sm font-medium ${
              message.startsWith("Could not")
                ? "text-[#E5484D]"
                : "text-[#14B86A]"
            }`}
          >
            {message}
          </p>
        )}
      </div>
    </section>
  );
}