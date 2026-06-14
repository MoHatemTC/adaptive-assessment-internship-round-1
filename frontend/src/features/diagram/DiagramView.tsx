"use client";

import { useState, useTransition, useRef } from "react";

type DiagramStatus = "pending" | "completed" | "failed";

interface DiagramResponse {
  id: string;
  user_id?: string | null;
  prompt: string;
  image_url?: string | null;
  status: DiagramStatus;
  created_at: string;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function generateDiagram(
  prompt: string,
  userId?: string,
): Promise<DiagramResponse> {
  const response = await fetch(`${API_BASE_URL}/diagram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, user_id: userId ?? null }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err?.detail || "Failed to generate diagram.");
  }
  return response.json();
}

function IconDiagram() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <path d="M14 17.5h3a3 3 0 0 0 0-6h-3" />
      <path d="M10 7h4" />
    </svg>
  );
}

function IconSparkle() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z" />
    </svg>
  );
}

function IconDownload() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function IconExpand() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="15 3 21 3 21 9" />
      <polyline points="9 21 3 21 3 15" />
      <line x1="21" y1="3" x2="14" y2="10" />
      <line x1="3" y1="21" x2="10" y2="14" />
    </svg>
  );
}

const SUGGESTIONS = [
  "Three-tier web application architecture",
  "REST API request/response flow",
  "PostgreSQL schema for a learning platform",
  "CI/CD pipeline with GitHub Actions",
  "Microservices with API gateway",
];

function Skeleton() {
  return (
    <div className="mt-6 animate-pulse space-y-3">
      <div className="h-5 w-1/3 rounded-full bg-[#E6EEFF]" />
      <div className="h-56 w-full rounded-2xl bg-[#E6EEFF]" />
      <div className="h-3 w-2/3 rounded-full bg-[#E6EEFF]" />
    </div>
  );
}

function Fullscreen({
  imageUrl,
  prompt,
  onClose,
}: {
  imageUrl: string;
  prompt: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#1F2430]/80 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl bg-[#FBFBFD] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[#D8DDF0] px-6 py-4">
          <p className="max-w-lg truncate text-sm font-semibold text-[#1F2430]">
            {prompt}
          </p>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-[#D8DDF0] text-sm text-[#343434] transition hover:border-[#004EFF] hover:text-[#004EFF]"
          >
            ✕
          </button>
        </div>
        <div className="flex flex-1 items-center justify-center overflow-auto bg-white p-8">
          <img
            src={imageUrl}
            alt="Diagram fullscreen"
            className="max-h-full max-w-full object-contain"
          />
        </div>
      </div>
    </div>
  );
}

interface DiagramViewProps {
  initialPrompt?: string;
  userId?: string;
}

export function DiagramView({ initialPrompt = "", userId }: DiagramViewProps) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [diagram, setDiagram] = useState<DiagramResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [isFullscreen, setIsFullscreen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  };

  const handleGenerate = () => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    setError(null);

    startTransition(async () => {
      try {
        const result = await generateDiagram(trimmed, userId);
        setDiagram(result);
      } catch (err: unknown) {
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong. Please try again.",
        );
      }
    });
  };

  const handleDownload = () => {
    if (!diagram?.image_url) return;
    const a = document.createElement("a");
    a.href = diagram.image_url;
    a.download = `diagram-${diagram.id.slice(0, 8)}.svg`;
    a.target = "_blank";
    a.click();
  };

  return (
    <>
      {isFullscreen && diagram?.image_url && (
        <Fullscreen
          imageUrl={diagram.image_url}
          prompt={diagram.prompt}
          onClose={() => setIsFullscreen(false)}
        />
      )}

      <section className="w-full max-w-2xl rounded-3xl border border-[#D8DDF0] bg-[#FBFBFD] p-6 shadow-sm">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <span className="inline-flex rounded-full bg-[#CCE0FF] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-[#004EFF]">
              Viz Tool
            </span>
            <h2 className="mt-4 text-2xl font-bold leading-tight text-[#1F2430]">
              Diagram Generator
            </h2>
            <p className="mt-1 text-sm text-[#343434]">
              Describe any system, flow, or architecture and get an instant
              visual.
            </p>
          </div>
          <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl bg-[#CCE0FF] text-[#004EFF]">
            <IconDiagram />
          </div>
        </div>

        {/* Textarea */}
        <div className="relative mb-3">
          <textarea
            ref={textareaRef}
            id="diagram-prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onInput={autoResize}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey))
                handleGenerate();
            }}
            placeholder='e.g. "Database schema for a learning platform with users, courses, and sessions"'
            rows={3}
            disabled={isPending}
            className="w-full resize-none rounded-2xl border border-[#D8DDF0] bg-white px-4 py-3 text-sm text-[#1F2430] placeholder-[#A0A8B8] outline-none transition focus:border-[#004EFF] focus:ring-2 focus:ring-[#004EFF]/10 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <p className="absolute bottom-3 right-3 text-[10px] text-[#A0A8B8]">
            ⌘↵ to generate
          </p>
        </div>

        {/* Suggestion chips */}
        <div className="mb-5 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setPrompt(s);
                textareaRef.current?.focus();
              }}
              disabled={isPending}
              className="inline-flex items-center gap-1.5 rounded-full bg-[#E6EEFF] px-3 py-1.5 text-xs font-semibold text-[#004EFF] transition hover:bg-[#CCE0FF] disabled:opacity-50"
            >
              <IconSparkle />
              {s}
            </button>
          ))}
        </div>

        {/* Generate button */}
        <button
          type="button"
          id="diagram-generate-btn"
          onClick={handleGenerate}
          disabled={isPending || !prompt.trim()}
          className="flex h-[43px] w-full items-center justify-center gap-2 rounded-lg bg-[#004EFF] px-6 text-sm font-semibold text-white transition hover:bg-[#3374FF] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isPending ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Generating diagram…
            </>
          ) : (
            <>
              <IconSparkle />
              Generate Diagram
            </>
          )}
        </button>

        {/* Error */}
        {error && (
          <div className="mt-4 flex items-start gap-3 rounded-2xl border border-[#E5484D]/30 bg-[#E5484D]/5 p-4">
            <span className="mt-0.5 text-[#E5484D]">⚠</span>
            <p className="text-sm font-medium text-[#E5484D]">{error}</p>
          </div>
        )}

        {/* Skeleton */}
        {isPending && !diagram && <Skeleton />}

        {/* Result */}
        {diagram && !isPending && (
          <div className="mt-6">
            {/* Status + actions row */}
            <div className="mb-3 flex items-center justify-between">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
                  diagram.status === "completed"
                    ? "bg-[#14B86A]/10 text-[#14B86A]"
                    : diagram.status === "failed"
                      ? "bg-[#E5484D]/10 text-[#E5484D]"
                      : "bg-[#FFB300]/10 text-[#FFB300]"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    diagram.status === "completed"
                      ? "bg-[#14B86A]"
                      : diagram.status === "failed"
                        ? "bg-[#E5484D]"
                        : "animate-pulse bg-[#FFB300]"
                  }`}
                />
                {diagram.status === "completed"
                  ? "Diagram ready"
                  : diagram.status === "failed"
                    ? "Generation failed"
                    : "Processing…"}
              </span>

              {diagram.status === "completed" && diagram.image_url && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleDownload}
                    title="Download SVG"
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-[#D8DDF0] text-[#343434] transition hover:border-[#004EFF] hover:text-[#004EFF]"
                  >
                    <IconDownload />
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsFullscreen(true)}
                    title="Fullscreen"
                    className="flex h-8 w-8 items-center justify-center rounded-full border border-[#D8DDF0] text-[#343434] transition hover:border-[#004EFF] hover:text-[#004EFF]"
                  >
                    <IconExpand />
                  </button>
                </div>
              )}
            </div>

            {/* Diagram image */}
            {diagram.status === "completed" && diagram.image_url ? (
              <div
                className="group relative cursor-zoom-in overflow-hidden rounded-2xl border border-[#D8DDF0] bg-white"
                onClick={() => setIsFullscreen(true)}
              >
                <img
                  src={diagram.image_url}
                  alt={`Diagram: ${diagram.prompt}`}
                  className="w-full object-contain p-4 transition duration-200 group-hover:scale-[1.01]"
                  style={{ minHeight: 180 }}
                />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 transition group-hover:opacity-100">
                  <span className="rounded-full bg-[#004EFF]/80 px-4 py-1.5 text-xs font-semibold text-white backdrop-blur-sm">
                    Click to expand
                  </span>
                </div>
              </div>
            ) : diagram.status === "failed" ? (
              <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-[#E5484D]/20 bg-[#E5484D]/5 py-10 text-center">
                <span className="text-2xl">⚠️</span>
                <p className="text-sm font-semibold text-[#E5484D]">
                  Diagram generation failed
                </p>
                <p className="text-xs text-[#343434]">
                  Try rephrasing your prompt.
                </p>
              </div>
            ) : null}

            {/* Prompt label */}
            <p className="mt-3 line-clamp-1 text-xs text-[#A0A8B8]">
              <span className="font-semibold text-[#343434]">Prompt: </span>
              {diagram.prompt}
            </p>
          </div>
        )}

        {/* Empty state */}
        {!diagram && !isPending && !error && (
          <div className="mt-6 flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[#D8DDF0] bg-[#E6EEFF]/30 py-10 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#CCE0FF] text-[#004EFF]">
              <IconDiagram />
            </div>
            <p className="text-sm font-semibold text-[#1F2430]">
              No diagram yet
            </p>
            <p className="max-w-xs text-xs text-[#A0A8B8]">
              Describe a system, architecture, or data flow above and click{" "}
              <strong>Generate Diagram</strong>.
            </p>
          </div>
        )}
      </section>
    </>
  );
}
