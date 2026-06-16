"use client";

import { useEffect, useState } from "react";

interface McqOption {
  label: string;
  text: string;
}

interface McqCardProps {
  questionId: string;
  questionText: string;
  options: McqOption[];
  onSubmit: (questionId: string, selectedOptionId: string) => void;
  isSubmitting: boolean;
}

/**
 * Presentational card that renders a single MCQ question.
 *
 * The component is controlled by its parent: it tracks only the locally selected
 * option and delegates submission via `onSubmit`. Grading is silent — the card
 * never displays correctness or score.
 */
export default function McqCard({
  questionId,
  questionText,
  options,
  onSubmit,
  isSubmitting,
}: McqCardProps) {
  const [selectedOptionId, setSelectedOptionId] = useState<string>("");

  useEffect(() => {
    setSelectedOptionId("");
  }, [questionId]);

  const handleSubmit = () => {
    if (!selectedOptionId || isSubmitting) {
      return;
    }

    onSubmit(questionId, selectedOptionId);
  };

  return (
    <section className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 font-[family-name:var(--font-jakarta)] shadow-sm">
      <h2 className="mb-6 text-[21px] font-semibold leading-[25px] text-[#1F2430]">
        {questionText}
      </h2>

      <div className="space-y-3">
        {options.map((option) => {
          const isSelected = selectedOptionId === option.label;

          return (
            <label
              key={option.label}
              className={`flex cursor-pointer items-start gap-3 rounded-[24px] border p-4 transition ${
                isSelected
                  ? "border-[#004EFF] bg-[#E6EEFF]"
                  : "border-[#D8DDF0] bg-[#FBFBFD] hover:border-[#3374FF]"
              }`}
            >
              <input
                type="radio"
                name={`mcq-${questionId}`}
                value={option.label}
                checked={isSelected}
                onChange={() => setSelectedOptionId(option.label)}
                disabled={isSubmitting}
                className="mt-1 h-4 w-4 accent-[#004EFF]"
              />

              <div className="flex flex-col gap-1">
                <span className="text-sm font-semibold leading-[18px] text-[#343434]">
                  {option.label}
                </span>

                <span className="text-sm font-medium leading-[20px] text-[#343434]">
                  {option.text}
                </span>
              </div>
            </label>
          );
        })}
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={isSubmitting || !selectedOptionId}
        className="mt-6 h-[43px] rounded-lg bg-[#004EFF] px-6 py-3 text-sm font-semibold text-[#FBFBFD] transition hover:bg-[#3374FF] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isSubmitting ? "Submitting..." : "Submit Answer"}
      </button>
    </section>
  );
}