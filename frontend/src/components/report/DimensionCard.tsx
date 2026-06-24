import type { DimensionRadarPoint } from "@/lib/report-api";

export interface DimensionCardProps {
  dimension: DimensionRadarPoint;
}

export function DimensionCard({ dimension }: DimensionCardProps) {
  const scoreLabel =
    dimension.score === null ? "N/A" : `${String(dimension.score)}/10`;

  return (
    <div className="rounded-xl border border-border bg-surface-muted p-4">
      <p className="text-xs uppercase tracking-wide text-neutral/50">
        {dimension.label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-neutral">{scoreLabel}</p>
    </div>
  );
}
