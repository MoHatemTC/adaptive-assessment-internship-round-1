"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getCodeConfig,
  updateCodeConfig,
  type PlatformChallengeConfig,
} from "@/lib/api";

const LANGUAGE_OPTIONS = [
  { id: "python", label: "Python", executable: true },
  { id: "javascript", label: "JavaScript", executable: true },
  { id: "typescript", label: "TypeScript", executable: true },
  { id: "java", label: "Java", executable: false },
  { id: "go", label: "Go", executable: false },
  { id: "csharp", label: "C#", executable: false },
  { id: "ruby", label: "Ruby", executable: false },
  { id: "rust", label: "Rust", executable: false },
  { id: "cpp", label: "C++", executable: false },
] as const;

const DEFAULT_CONFIG: PlatformChallengeConfig = {
  challenge: {
    categories: ["algorithms", "data_structures", "strings", "arrays"],
    difficulty_levels: ["beginner", "intermediate", "advanced"],
    challenges_per_candidate: 2,
    total_time_minutes: 90,
    min_time_per_challenge_minutes: 10,
    max_time_per_challenge_minutes: 45,
    duration_minutes: 20,
    min_complexity: 1,
    max_complexity: 5,
    default_language: "python",
    allowed_languages: ["python", "javascript", "typescript"],
    domain: "Programming",
    e2b_execution_timeout_seconds: 30,
    e2b_template: "code-interpreter-v1",
  },
};

export default function AdminPage() {
  const [config, setConfig] = useState<PlatformChallengeConfig>(DEFAULT_CONFIG);
  const [adminKey, setAdminKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCodeConfig()
      .then((loaded) => {
        setConfig({
          challenge: {
            ...DEFAULT_CONFIG.challenge,
            ...loaded.challenge,
            allowed_languages:
              loaded.challenge.allowed_languages?.length > 0
                ? loaded.challenge.allowed_languages
                : DEFAULT_CONFIG.challenge.allowed_languages,
          },
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed"))
      .finally(() => setLoading(false));
  }, []);

  const updateField = useCallback(
    (field: keyof PlatformChallengeConfig["challenge"], value: string | number | string[]) => {
      setConfig((prev) => ({
        challenge: { ...prev.challenge, [field]: value },
      }));
    },
    [],
  );

  const toggleAllowedLanguage = useCallback((languageId: string) => {
    setConfig((prev) => {
      const current = new Set(prev.challenge.allowed_languages ?? []);
      if (current.has(languageId)) {
        current.delete(languageId);
      } else {
        current.add(languageId);
      }
      const allowed = Array.from(current);
      const defaultLanguage = allowed.includes(prev.challenge.default_language)
        ? prev.challenge.default_language
        : allowed[0] ?? "python";
      return {
        challenge: {
          ...prev.challenge,
          allowed_languages: allowed,
          default_language: defaultLanguage,
        },
      };
    });
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await updateCodeConfig(config, adminKey || undefined);
      setConfig(saved);
      setMessage("Configuration saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [adminKey, config]);

  if (loading) {
    return (
      <main className="mx-auto max-w-2xl p-6 text-sm text-neutral/70">Loading admin config…</main>
    );
  }

  const c = config.challenge;
  const allowedSet = new Set(c.allowed_languages ?? []);

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-neutral">Code assessment admin</h1>
        <p className="mt-1 text-sm text-neutral/70">
          Global timing, language, and generation settings for multi-challenge timed sessions.
        </p>
      </header>

      {error && (
        <div className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-lg border border-success/30 bg-success/5 p-4 text-sm text-success">
          {message}
        </div>
      )}

      <section className="space-y-4 rounded-xl border border-border bg-white p-6 shadow-sm">
        <label className="block text-sm">
          Admin key (X-Admin-Key, optional in dev)
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-border px-3 py-2"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
          />
        </label>

        <div className="space-y-2">
          <p className="text-sm font-medium text-neutral">Allowed languages</p>
          <p className="text-xs text-neutral/60">
            Generation uses profile skills intersected with this list. Languages marked
            &quot;sandbox&quot; can be executed in E2B today.
          </p>
          <div className="flex flex-wrap gap-2">
            {LANGUAGE_OPTIONS.map((language) => {
              const checked = allowedSet.has(language.id);
              return (
                <label
                  key={language.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
                    checked
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-neutral/70"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={checked}
                    onChange={() => toggleAllowedLanguage(language.id)}
                  />
                  {language.label}
                  {language.executable ? (
                    <span className="rounded bg-success/10 px-1.5 text-[10px] text-success">
                      sandbox
                    </span>
                  ) : (
                    <span className="rounded bg-surface-muted px-1.5 text-[10px] text-neutral/50">
                      gen only
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        </div>

        <label className="block text-sm">
          Default language (fallback when profile skills do not match)
          <select
            className="mt-1 w-full rounded-lg border border-border px-3 py-2"
            value={c.default_language}
            onChange={(e) => updateField("default_language", e.target.value)}
          >
            {(c.allowed_languages ?? []).map((languageId) => (
              <option key={languageId} value={languageId}>
                {LANGUAGE_OPTIONS.find((item) => item.id === languageId)?.label ?? languageId}
              </option>
            ))}
          </select>
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            Challenges per candidate
            <input
              type="number"
              min={1}
              max={10}
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={c.challenges_per_candidate}
              onChange={(e) => updateField("challenges_per_candidate", Number(e.target.value))}
            />
          </label>
          <label className="block text-sm">
            Total time (minutes)
            <input
              type="number"
              min={10}
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={c.total_time_minutes}
              onChange={(e) => updateField("total_time_minutes", Number(e.target.value))}
            />
          </label>
          <label className="block text-sm">
            Min time per challenge (min)
            <input
              type="number"
              min={5}
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={c.min_time_per_challenge_minutes}
              onChange={(e) =>
                updateField("min_time_per_challenge_minutes", Number(e.target.value))
              }
            />
          </label>
          <label className="block text-sm">
            Max time per challenge (min)
            <input
              type="number"
              min={5}
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={c.max_time_per_challenge_minutes}
              onChange={(e) =>
                updateField("max_time_per_challenge_minutes", Number(e.target.value))
              }
            />
          </label>
          <label className="block text-sm">
            E2B execution timeout (sec)
            <input
              type="number"
              min={5}
              max={120}
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={c.e2b_execution_timeout_seconds}
              onChange={(e) =>
                updateField("e2b_execution_timeout_seconds", Number(e.target.value))
              }
            />
          </label>
          <label className="block text-sm">
            E2B template
            <input
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={c.e2b_template}
              onChange={(e) => updateField("e2b_template", e.target.value)}
            />
          </label>
        </div>

        <button
          type="button"
          disabled={saving || allowedSet.size === 0}
          onClick={handleSave}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-60 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save configuration"}
        </button>
      </section>
    </main>
  );
}
