"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  AssessmentRead,
  Blueprint,
  ToolBlueprint,
  getAssessment,
} from "@/lib/admin-api";

function parseBlueprint(row: AssessmentRead): Blueprint | null {
  const bp = row.blueprint_json as Partial<Blueprint>;
  if (typeof bp.total_questions !== "number" || !bp.tools) return null;
  return bp as Blueprint;
}

export default function AdminDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [row, setRow] = useState<AssessmentRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!id) return;
    getAssessment(id)
      .then(setRow)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
  }, [id]);

  const shareUrl =
    typeof window !== "undefined" ? `${window.location.origin}/assessment/${id}` : "";

  const copyLink = useCallback(() => {
    if (!shareUrl) return;
    void navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [shareUrl]);

  if (loading) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl px-4 py-8">
        <p className="text-sm text-[#1F2430]/70">Loading…</p>
      </main>
    );
  }

  if (error || !row) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl px-4 py-8">
        <p className="rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-3 text-sm text-[#E5484D]">
          {error ?? "Assessment not found"}
        </p>
      </main>
    );
  }

  const blueprint = parseBlueprint(row);
  const enabledTools: [string, ToolBlueprint][] = blueprint
    ? Object.entries(blueprint.tools).filter(([, cfg]) => cfg.enabled)
    : [];

  return (
    <main className="mx-auto min-h-screen max-w-2xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold text-[#1F2430]">{row.title}</h1>
        <p className="mt-1 text-sm text-[#1F2430]/70">
          {blueprint?.description ?? row.prompt}
        </p>
        <p className="mt-2 text-xs text-[#1F2430]/60">Status: {row.status}</p>
      </header>

      {blueprint ? (
        <section className="rounded-xl border border-[#D8DDF0] bg-[#FBFBFD] p-5">
          <p className="text-sm text-[#1F2430]">
            <span className="font-medium">Total questions:</span>{" "}
            {blueprint.total_questions}
          </p>
          <ul className="mt-3 space-y-1 text-sm text-[#1F2430]">
            {enabledTools.map(([tool, cfg]) => (
              <li key={tool}>
                <span className="font-medium capitalize">{tool}</span>:{" "}
                {cfg.question_count} question(s), {cfg.min_difficulty}–
                {cfg.max_difficulty}
              </li>
            ))}
          </ul>
        </section>
      ) : (
        <p className="text-sm text-[#1F2430]/70">
          No blueprint generated yet for this assessment.
        </p>
      )}

      <section className="rounded-xl border border-[#D8DDF0] bg-white p-5">
        <p className="mb-2 text-sm font-medium text-[#1F2430]">Shareable link</p>
        <div className="flex items-center gap-2">
          <code className="flex-1 truncate rounded bg-[#E6EEFF] px-2 py-1 text-sm">
            {shareUrl}
          </code>
          <button
            type="button"
            onClick={copyLink}
            className="rounded-lg border border-[#D8DDF0] px-3 py-1 text-sm hover:bg-[#E6EEFF]"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </section>

      <Link
        href={`/admin/${id}/results`}
        className="inline-block rounded-lg border border-[#D8DDF0] px-4 py-2 text-sm font-medium text-[#1F2430] hover:bg-[#E6EEFF]"
      >
        View Results
      </Link>
    </main>
  );
}
