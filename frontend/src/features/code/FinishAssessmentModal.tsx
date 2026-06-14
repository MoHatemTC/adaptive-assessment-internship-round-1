"use client";

export interface FinishAssessmentModalProps {
  open: boolean;
  challengesSubmitted: number;
  challengesTotal: number;
  unsubmittedCount: number;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: (confirmUnsubmitted: boolean) => void;
}

export function FinishAssessmentModal({
  open,
  challengesSubmitted,
  challengesTotal,
  unsubmittedCount,
  loading = false,
  onCancel,
  onConfirm,
}: FinishAssessmentModalProps) {
  if (!open) {
    return null;
  }

  const hasUnsubmitted = unsubmittedCount > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-neutral/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="finish-assessment-title"
    >
      <div className="w-full max-w-md rounded-xl border border-border bg-white p-6 shadow-xl">
        <h2 id="finish-assessment-title" className="text-lg font-semibold text-neutral">
          Finish assessment?
        </h2>
        <p className="mt-2 text-sm text-neutral/80">
          You have submitted <strong>{challengesSubmitted}</strong> of{" "}
          <strong>{challengesTotal}</strong> challenge(s) for grading.
        </p>
        {hasUnsubmitted && (
          <p className="mt-3 rounded-lg border border-tertiary/30 bg-tertiary/10 p-3 text-sm text-neutral">
            <strong>{unsubmittedCount}</strong> challenge(s) were not submitted. Unsubmitted work
            will <strong>not</strong> be graded. You cannot edit answers after finishing.
          </p>
        )}
        {!hasUnsubmitted && (
          <p className="mt-3 text-sm text-neutral/70">
            After you finish, the assessment will be locked and your results will be finalized.
          </p>
        )}
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            disabled={loading}
            onClick={onCancel}
            className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-neutral hover:bg-surface-muted disabled:opacity-50"
          >
            Continue working
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => onConfirm(hasUnsubmitted)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-60 disabled:opacity-50"
          >
            {loading ? "Finishing…" : "Finish assessment"}
          </button>
        </div>
      </div>
    </div>
  );
}
