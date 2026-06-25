"use client";

import { useState } from "react";

export interface McqOption {
  label: string;
  text: string;
}

interface McqCardProps {
  questionId: number;
  questionText: string;
  options: McqOption[];
  onSubmit: (questionId: number, selectedLabel: string) => void;
  isSubmitting: boolean;
}

/**
 * Presentational card that renders a single MCQ question.
 *
 * The component is fully controlled by its parent: it tracks only the locally
 * selected option label and delegates submission via `onSubmit`. Grading is
 * silent — the card never displays correctness or score, and the options carry
 * no answer key.
 */
export default function McqCard({
  questionId,
  questionText,
  options,
  onSubmit,
  isSubmitting,
}: McqCardProps) {
  const [selectedLabel, setSelectedLabel] = useState<string>("");

  const handleSubmit = () => {
    if (!selectedLabel || isSubmitting) {
      return;
    }
    onSubmit(questionId, selectedLabel);
  };

  return (
    <section className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 font-[family-name:var(--font-jakarta)] shadow-sm">
      <h2 className="mb-6 text-[21px] font-semibold leading-[25px] text-[#1F2430]">
        {questionText}
      </h2>

      <div className="space-y-3">
        {options.map((option) => {
          const isSelected = selectedLabel === option.label;

          return (
            <label
              key={option.label}
              className={`flex cursor-pointer items-center gap-3 rounded-[24px] border p-4 transition ${
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
                onChange={() => setSelectedLabel(option.label)}
                disabled={isSubmitting}
                className="h-4 w-4 accent-[#004EFF]"
              />

              <span className="text-sm font-semibold leading-[18px] text-[#343434]">
                {option.label}.
              </span>

              <span className="text-sm leading-[18px] text-[#343434]">
                {option.text}
              </span>
            </label>
          );
        })}
      </div>

      <button
        type="button"
        onClick={handleSubmit}
        disabled={isSubmitting || !selectedLabel}
        className="mt-6 h-[43px] rounded-lg bg-[#004EFF] px-6 py-3 text-sm font-semibold text-[#FBFBFD] transition hover:bg-[#3374FF] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isSubmitting ? "Submitting..." : "Submit Answer"}
      </button>
    </section>
  );
}
