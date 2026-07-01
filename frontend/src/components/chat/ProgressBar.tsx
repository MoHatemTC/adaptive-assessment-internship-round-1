export interface ProgressBarProps {
  current: number;
  total: number;
  label?: string;
}

export function ProgressBar({ current, total, label }: ProgressBarProps) {
  const pct = total > 0 ? Math.round(((current + 1) / total) * 100) : 0;

  return (
    <div className="flex items-center gap-3">
      {label && (
        <span className="whitespace-nowrap text-xs text-[#1F2430]/70">
          {label}
        </span>
      )}
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#E6EEFF]">
        <div
          className="h-full rounded-full bg-[#004EFF] transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="whitespace-nowrap text-xs font-medium tabular-nums text-[#1F2430]/70">
        {current + 1}/{total}
      </span>
    </div>
  );
}
