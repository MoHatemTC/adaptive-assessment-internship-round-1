"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import {
  BlueprintGenerateResponse,
  createAssessment,
  generateBlueprint,
} from "@/lib/admin-api";

const TOOLS: { key: string; label: string }[] = [
  { key: "mcq", label: "MCQ" },
  { key: "voice", label: "Voice" },
  { key: "diagram", label: "Diagram" },
  { key: "code", label: "Code" },
];

export default function AdminNewPage() {
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [selected, setSelected] = useState<Record<string, boolean>>({
    mcq: true,
    voice: false,
    diagram: false,
    code: false,
  });
  const [cvRequired, setCvRequired] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BlueprintGenerateResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const toggle = (key: string) =>
    setSelected((prev) => ({ ...prev, [key]: !prev[key] }));

  const handleSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      setLoading(true);
      setError(null);
      setResult(null);
      try {
        const created = await createAssessment({
          title: title.trim(),
          prompt: prompt.trim(),
          tool_config: selected,
          cv_required: cvRequired,
        });
        const generated = await generateBlueprint(created.id);
        setResult(generated);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Creation failed");
      } finally {
        setLoading(false);
      }
    },
    [title, prompt, selected, cvRequired],
  );

  const shareUrl =
    result && typeof window !== "undefined"
      ? `${window.location.origin}${result.shareable_link}`
      : (result?.shareable_link ?? "");

  const copyLink = useCallback(() => {
    if (!shareUrl) return;
    void navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [shareUrl]);

  return (
    <main className="mx-auto min-h-screen max-w-2xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold text-[#1F2430]">New assessment</h1>
        <p className="mt-1 text-sm text-[#1F2430]/70">
          Describe what to test and pick tools. The planner builds the blueprint.
        </p>
      </header>

      {!result && (
        <form onSubmit={handleSubmit} className="space-y-5">
          <label className="block text-sm text-[#1F2430]">
            <span className="mb-1 block font-medium">Title</span>
            <input
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-lg border border-[#D8DDF0] bg-white px-3 py-2"
              required
            />
          </label>

          <label className="block text-sm text-[#1F2430]">
            <span className="mb-1 block font-medium">
              What should this assessment test?
            </span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={5}
              className="w-full rounded-lg border border-[#D8DDF0] bg-white px-3 py-2"
              required
            />
          </label>

          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium text-[#1F2430]">
              Tools
            </legend>
            <div className="flex flex-wrap gap-3">
              {TOOLS.map((tool) => (
                <label
                  key={tool.key}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                    selected[tool.key]
                      ? "border-[#004EFF] bg-[#E6EEFF] text-[#1F2430]"
                      : "border-[#D8DDF0] bg-white text-[#1F2430]/70"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected[tool.key] ?? false}
                    onChange={() => toggle(tool.key)}
                    className="h-4 w-4 accent-[#004EFF]"
                  />
                  {tool.label}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="mt-4">
            <p className="text-sm font-medium text-[#1F2430]">CV Upload</p>
            <div className="mt-2 flex gap-3">
              <button
                type="button"
                onClick={() => setCvRequired(false)}
                className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
                  !cvRequired
                    ? "border-[#004EFF] bg-[#CCE0FF] text-[#004EFF]"
                    : "border-[#D8DDF0] bg-white text-[#1F2430]"
                }`}
              >
                Optional
              </button>
              <button
                type="button"
                onClick={() => setCvRequired(true)}
                className={`rounded-lg border px-4 py-2 text-sm font-medium transition ${
                  cvRequired
                    ? "border-[#004EFF] bg-[#CCE0FF] text-[#004EFF]"
                    : "border-[#D8DDF0] bg-white text-[#1F2430]"
                }`}
              >
                Required
              </button>
            </div>
            <p className="mt-1 text-xs text-[#606575]">
              {cvRequired
                ? "Learners must upload their CV to start this assessment."
                : "Learners can optionally upload their CV."}
            </p>
          </div>

          {error && (
            <p className="rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-3 text-sm text-[#E5484D]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-[#004EFF] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#3374FF] disabled:opacity-50"
          >
            {loading ? "Generating…" : "Create & Generate Blueprint"}
          </button>
        </form>
      )}

      {result && (
        <section className="space-y-5">
          <div className="rounded-xl border border-[#D8DDF0] bg-[#FBFBFD] p-5">
            <h2 className="text-lg font-semibold text-[#1F2430]">
              {result.blueprint.title}
            </h2>
            <p className="mt-1 text-sm text-[#1F2430]/70">
              {result.blueprint.description}
            </p>
            <p className="mt-3 text-sm text-[#1F2430]">
              <span className="font-medium">Total questions:</span>{" "}
              {result.blueprint.total_questions}
            </p>
            <ul className="mt-3 space-y-1 text-sm text-[#1F2430]">
              {Object.entries(result.blueprint.tools)
                .filter(([, cfg]) => cfg.enabled)
                .map(([tool, cfg]) => (
                  <li key={tool}>
                    <span className="font-medium capitalize">{tool}</span>:{" "}
                    {cfg.question_count} question(s), {cfg.min_difficulty}–
                    {cfg.max_difficulty}
                  </li>
                ))}
            </ul>
          </div>

          <div className="rounded-xl border border-[#D8DDF0] bg-white p-5">
            <p className="mb-2 text-sm font-medium text-[#1F2430]">
              Shareable link
            </p>
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
          </div>

          <div className="flex gap-3">
            <Link
              href={`/admin/${result.assessment_id}/results`}
              className="rounded-lg border border-[#D8DDF0] px-4 py-2 text-sm font-medium text-[#1F2430] hover:bg-[#E6EEFF]"
            >
              View Results
            </Link>
            <Link
              href="/admin"
              className="rounded-lg border border-[#D8DDF0] px-4 py-2 text-sm font-medium text-[#1F2430] hover:bg-[#E6EEFF]"
            >
              All assessments
            </Link>
          </div>
        </section>
      )}
    </main>
  );
}
