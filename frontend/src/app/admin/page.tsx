"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  AssessmentRead,
  getShareableLink,
  listAssessments,
} from "@/lib/admin-api";

function totalQuestions(row: AssessmentRead): number | null {
  const bp = row.blueprint_json as { total_questions?: unknown };
  return typeof bp.total_questions === "number" ? bp.total_questions : null;
}

export default function AdminPage() {
  const [rows, setRows] = useState<AssessmentRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    listAssessments()
      .then(setRows)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
  }, []);

  const copyLink = useCallback(async (id: string) => {
    try {
      const { shareable_link } = await getShareableLink(id);
      const url = `${window.location.origin}${shareable_link}`;
      await navigator.clipboard.writeText(url);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not get link");
    }
  }, []);

  return (
    <main className="mx-auto min-h-screen max-w-4xl space-y-6 px-4 py-8">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-[#1F2430]">Assessments</h1>
        <Link
          href="/admin/new"
          className="rounded-lg bg-[#004EFF] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#3374FF]"
        >
          New assessment
        </Link>
      </header>

      {error && (
        <p className="rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-3 text-sm text-[#E5484D]">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-[#1F2430]/70">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-[#1F2430]/70">
          No assessments yet. Create one to get started.
        </p>
      ) : (
        <ul className="divide-y divide-[#D8DDF0] rounded-xl border border-[#D8DDF0] bg-[#FBFBFD]">
          {rows.map((row) => {
            const total = totalQuestions(row);
            return (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-3 p-4"
              >
                <div>
                  <Link
                    href={`/admin/${row.id}`}
                    className="font-medium text-[#1F2430] hover:text-[#004EFF]"
                  >
                    {row.title}
                  </Link>
                  <p className="text-xs text-[#1F2430]/60">
                    {row.status}
                    {total !== null ? ` · ${total} questions` : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void copyLink(row.id)}
                    disabled={row.status !== "active"}
                    className="rounded-lg border border-[#D8DDF0] px-3 py-1 text-sm text-[#1F2430] hover:bg-[#E6EEFF] disabled:opacity-50"
                  >
                    {copiedId === row.id ? "Copied" : "Get link"}
                  </button>
                  <Link
                    href={`/admin/${row.id}/results`}
                    className="rounded-lg border border-[#D8DDF0] px-3 py-1 text-sm text-[#1F2430] hover:bg-[#E6EEFF]"
                  >
                    Results
                  </Link>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
