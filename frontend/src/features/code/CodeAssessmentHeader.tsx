"use client";

export interface CodeAssessmentHeaderProps {
  questionNumber: number;
  totalQuestions: number;
  secondsRemaining: number | null;
  onExit?: () => void;
}

function formatTimer(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function CodeAssessmentHeader({
  questionNumber,
  totalQuestions,
  secondsRemaining,
  onExit,
}: CodeAssessmentHeaderProps) {
  const progress =
    totalQuestions > 0
      ? Math.min(100, Math.round((questionNumber / totalQuestions) * 100))
      : 0;

  return (
    <header className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-border-base bg-surface px-gutter shadow-sm">
      <div className="flex items-center gap-xs">
        <button
          type="button"
          onClick={onExit}
          aria-label="Exit Assessment"
          className="flex items-center gap-xs text-label-md text-on-surface-variant transition hover:text-on-surface"
        >
          <span className="material-symbols-outlined text-[20px]">close</span>
          Exit
        </button>
      </div>

      <div className="flex flex-1 items-center justify-center px-lg">
        <div className="flex w-full max-w-2xl items-center gap-sm">
          <span className="whitespace-nowrap text-label-sm text-on-surface-variant">
            Question {questionNumber} of {totalQuestions}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-container-high">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="whitespace-nowrap text-label-sm text-on-surface-variant">
            {progress}%
          </span>
        </div>
      </div>

      <div className="flex items-center gap-xs text-on-surface-variant">
        <span className="material-symbols-outlined text-[20px]">timer</span>
        <span className="text-label-md">
          {secondsRemaining == null ? "--:--" : formatTimer(secondsRemaining)}
        </span>
      </div>
    </header>
  );
}
