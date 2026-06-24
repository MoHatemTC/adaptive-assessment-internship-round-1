"use client";

import { useEffect, useState } from "react";

import { DimensionCard } from "@/components/report/DimensionCard";
import { SkillRadarChart } from "@/components/report/RadarChart";
import {
  getSessionRadarReport,
  type SessionRadarReport,
} from "@/lib/report-api";

export interface SessionRadarReportViewProps {
  sessionId: string;
  title?: string;
}

export function SessionRadarReportView({
  sessionId,
  title = "Your skill profile",
}: SessionRadarReportViewProps) {
  const [report, setReport] = useState<SessionRadarReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await getSessionRadarReport(sessionId);
        if (!cancelled) setReport(loaded);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load report");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loading) {
    return <p className="text-sm text-neutral/70">Generating your report…</p>;
  }

  if (error || !report) {
    return (
      <div className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">
        {error ?? "Report unavailable"}
      </div>
    );
  }

  const hasScores = report.dimensions.some((dim) => dim.score !== null);

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h2 className="text-xl font-semibold text-neutral">{title}</h2>
        <p className="text-sm text-neutral/80">{report.summary}</p>
        <div className="flex flex-wrap gap-2 text-xs text-neutral/60">
          {report.overall_score !== null ? (
            <span className="rounded-full bg-primary/10 px-3 py-1 text-primary">
              Overall {report.overall_score}/10
            </span>
          ) : null}
          <span className="rounded-full bg-surface-muted px-3 py-1">
            {report.questions_answered} question(s) assessed
          </span>
          {report.tools_used.map((tool) => (
            <span key={tool} className="rounded-full bg-surface-muted px-3 py-1">
              {tool}
            </span>
          ))}
        </div>
      </header>

      {hasScores ? (
        <>
          <SkillRadarChart dimensions={report.dimensions} />
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {report.dimensions.map((dimension) => (
              <DimensionCard key={dimension.name} dimension={dimension} />
            ))}
          </div>
        </>
      ) : (
        <p className="text-sm text-neutral/70">
          Complete at least one assessed question to see your radar chart.
        </p>
      )}

      {report.strengths.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold text-neutral">Strengths</h3>
          <p className="mt-1 text-sm text-neutral/80">
            {report.strengths.join(", ")}
          </p>
        </section>
      ) : null}

      {report.growth_areas.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold text-neutral">Areas to develop</h3>
          <p className="mt-1 text-sm text-neutral/80">
            {report.growth_areas.join(", ")}
          </p>
        </section>
      ) : null}

      {report.evidence_highlights.length > 0 ? (
        <section>
          <h3 className="text-sm font-semibold text-neutral">Evidence highlights</h3>
          <ul className="mt-2 space-y-2 text-sm text-neutral/80">
            {report.evidence_highlights.map((item) => (
              <li
                key={item}
                className="rounded-lg border border-border bg-white px-3 py-2"
              >
                {item}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
