"use client";

import { useCallback, useEffect, useState } from "react";

import { IntegrityMonitor } from "@/components/proctoring/IntegrityMonitor";
import { ProctoringGate } from "@/components/proctoring/ProctoringGate";
import { CodeTool } from "@/components/tools/CodeTool";
import { ChallengeNavigator } from "@/features/code/ChallengeNavigator";
import { ExaminerChannel } from "@/integrations/ExaminerChannel";
import { SessionSummary } from "@/features/code/SessionSummary";
import { SubmissionResults } from "@/features/code/SubmissionResults";
import { FinishAssessmentModal } from "@/features/code/FinishAssessmentModal";
import { IntegrityReportCard } from "@/features/proctoring/IntegrityReportCard";
import { useSessionPoll } from "@/hooks/useSessionPoll";
import {
  completeCodeSession,
  getIntegrityReport,
  getSessionSubmissions,
  startAdaptiveSession,
  startCodeSession,
  type SessionCompletionRead,
  type SubmissionRead,
  type AdaptiveSubmitResponse,
  type UserProfile,
} from "@/lib/api";
import type { IntegrityReport } from "@/types/proctoring";

const PROGRESS_KEY = "masaar-last-evaluation";

export default function AssessmentPage() {
  const [step, setStep] = useState<"profile" | "secure" | "challenge" | "done">("profile");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [skills, setSkills] = useState("Python");
  const [experienceLevel, setExperienceLevel] = useState("intermediate");
  const [objectives, setObjectives] = useState("Practice algorithms and problem solving");

  const [sessionId, setSessionId] = useState<string | null>(null);
  const { session, setSession, refresh, error: pollError } = useSessionPoll(
    sessionId,
    step === "secure" || step === "challenge" || step === "done",
  );
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<SubmissionRead | null>(null);
  const [allSubmissions, setAllSubmissions] = useState<SubmissionRead[]>([]);
  const [integrityReport, setIntegrityReport] = useState<IntegrityReport | null>(null);
  const [finishModalOpen, setFinishModalOpen] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [completionSummary, setCompletionSummary] = useState<SessionCompletionRead | null>(
    null,
  );
  const [adaptiveMode] = useState(true);
  const [adaptiveStatus, setAdaptiveStatus] = useState<string | null>(null);

  const selected =
    session?.challenges.find((c) => c.challenge_id === selectedId) ??
    session?.challenges[0] ??
    null;

  useEffect(() => {
    if (session && selectedId === null && session.challenges[0]) {
      setSelectedId(session.challenges[0].challenge_id);
    }
  }, [session, selectedId]);

  useEffect(() => {
    if (session?.status === "expired" && step === "challenge") {
      setError("Assessment session has expired.");
    }
  }, [session?.status, step]);

  const loadSessionSubmissions = useCallback(async (id: string) => {
    const data = await getSessionSubmissions(id);
    setAllSubmissions(data.submissions);
    return data.submissions;
  }, []);

  const handleStartSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSelectedId(null);
    setAllSubmissions([]);
    setIntegrityReport(null);
    try {
      const prior = localStorage.getItem(PROGRESS_KEY);
      const profile: UserProfile = {
        name: name.trim() || "Learner",
        skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        experience_level: experienceLevel,
        preferred_domains: ["Programming"],
        learning_objectives: [objectives],
        prior_performance_summary: prior ?? undefined,
      };
      const startSession = adaptiveMode ? startAdaptiveSession : startCodeSession;
      const result = await startSession(profile);
      setSessionId(result.session_id);
      setSession(result);
      setSelectedId(result.challenges[0]?.challenge_id ?? null);
      setStep("secure");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session start failed");
    } finally {
      setLoading(false);
    }
  }, [adaptiveMode, name, skills, experienceLevel, objectives, setSession]);

  const handleAdaptiveSubmitted = useCallback(
    async (result: AdaptiveSubmitResponse) => {
      setAdaptiveStatus(result.message);
      setLastResult(null);
      const updated = await refresh();
      if (updated) {
        const next = updated.challenges.find((challenge) => !challenge.submitted);
        if (next) {
          setSelectedId(next.challenge_id);
        }
      }
      if (result.session_complete && sessionId) {
        setFinishModalOpen(true);
      }
    },
    [refresh, sessionId],
  );

  const handleSubmitted = useCallback(
    async (result: SubmissionRead) => {
      setLastResult(result);
      const summary = [
        result.evaluation_status,
        result.evaluation_score != null ? `score ${result.evaluation_score}/100` : null,
        result.next_difficulty ? `next ${result.next_difficulty}` : null,
      ]
        .filter(Boolean)
        .join(", ");
      if (summary) {
        localStorage.setItem(PROGRESS_KEY, summary);
      }

      const updated = await refresh();
      if (sessionId) {
        await loadSessionSubmissions(sessionId);
      }
      if (updated && updated.challenges.length > 1) {
        const next = updated.challenges.find((challenge) => !challenge.submitted);
        if (next) {
          setSelectedId(next.challenge_id);
        }
      }
    },
    [loadSessionSubmissions, refresh, sessionId],
  );

  const submittedCount = session?.challenges.filter((c) => c.submitted).length ?? 0;
  const totalChallenges =
    session?.total_questions ?? session?.challenges.length ?? 0;
  const unsubmittedCount = totalChallenges - submittedCount;
  const sessionLocked = session?.status === "completed";

  const handleFinishAssessment = useCallback(
    async (confirmUnsubmitted: boolean) => {
      if (!sessionId) return;
      setFinishing(true);
      setError(null);
      try {
        const summary = await completeCodeSession(sessionId, confirmUnsubmitted);
        setCompletionSummary(summary);
        const report = await getIntegrityReport(sessionId);
        setIntegrityReport(report);
        const submissions = await loadSessionSubmissions(sessionId);
        setAllSubmissions(submissions);
        await refresh();
        setFinishModalOpen(false);
        setStep("done");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not finish assessment");
      } finally {
        setFinishing(false);
      }
    },
    [loadSessionSubmissions, refresh, sessionId],
  );

  useEffect(() => {
    if (step === "done" && sessionId && allSubmissions.length === 0) {
      loadSessionSubmissions(sessionId).catch(() => undefined);
    }
  }, [step, sessionId, allSubmissions.length, loadSessionSubmissions]);

  const displayError = error ?? pollError;

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-3xl font-bold text-neutral">Masaar Code Assessment</h1>
        <p className="mt-1 text-sm text-neutral/70">
          Profile → secure mode → adaptive challenges (silent submit) → Finish
        </p>
        {session && (
          <p className="mt-1 text-xs text-neutral/50">Session: {session.session_id}</p>
        )}
      </header>

      <nav className="flex gap-3 text-sm">
        <span className={step === "profile" ? "font-semibold text-primary" : "text-neutral/60"}>
          1. Profile
        </span>
        <span className="text-neutral/40">→</span>
        <span className={step === "secure" ? "font-semibold text-primary" : "text-neutral/60"}>
          2. Secure mode
        </span>
        <span className="text-neutral/40">→</span>
        <span className={step === "challenge" ? "font-semibold text-primary" : "text-neutral/60"}>
          3. Challenges
        </span>
        <span className="text-neutral/40">→</span>
        <span className={step === "done" ? "font-semibold text-primary" : "text-neutral/60"}>
          4. Results
        </span>
      </nav>

      {displayError && (
        <div className="rounded-lg border border-error/30 bg-error/5 p-4 text-sm text-error">
          {displayError}
        </div>
      )}

      {step === "profile" && (
        <section className="space-y-4 rounded-xl border border-border bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Your profile</h2>
          <label className="block text-sm">
            Name
            <input
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Alex"
            />
          </label>
          <label className="block text-sm">
            Skills (comma-separated)
            <input
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
              placeholder="Python, JavaScript, TypeScript"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              Challenges are generated in languages that match your skills (Python, JavaScript, and
              TypeScript run in the sandbox today).
            </span>
          </label>
          <label className="block text-sm">
            Experience level
            <select
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              value={experienceLevel}
              onChange={(e) => setExperienceLevel(e.target.value)}
            >
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </label>
          <label className="block text-sm">
            Learning objectives
            <textarea
              className="mt-1 w-full rounded-lg border border-border px-3 py-2"
              rows={2}
              value={objectives}
              onChange={(e) => setObjectives(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={loading}
            onClick={handleStartSession}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-60 disabled:opacity-50"
          >
            {loading ? "Starting session…" : "Start timed assessment (multiple challenges)"}
          </button>
          <p className="text-xs text-neutral/60">
            You will receive a set of personalized challenges. Submit each one, then finish the
            assessment when you are done.
          </p>
        </section>
      )}

      {step === "secure" && sessionId && (
        <ProctoringGate sessionId={sessionId} onReady={() => setStep("challenge")} />
      )}

      <IntegrityMonitor
        sessionId={sessionId}
        enabled={step === "challenge" && session?.status === "active"}
        strict
      />

      {sessionId && (step === "secure" || step === "challenge") && (
        <ExaminerChannel
          sessionId={sessionId}
          enabled={session?.status === "active"}
          compact={step === "challenge"}
          showIdleMessage={step === "challenge"}
          blockClipboard
          onCodeSubmitted={handleSubmitted}
        />
      )}

      <FinishAssessmentModal
        open={finishModalOpen}
        challengesSubmitted={submittedCount}
        challengesTotal={totalChallenges}
        unsubmittedCount={unsubmittedCount}
        loading={finishing}
        onCancel={() => setFinishModalOpen(false)}
        onConfirm={handleFinishAssessment}
      />

      {step === "challenge" && session && (
        <div className="space-y-3 rounded-lg border border-border bg-white px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-neutral/80">
              Progress: {submittedCount} of {totalChallenges} challenge(s) submitted for grading.
            </p>
            {!sessionLocked && (
              <button
                type="button"
                onClick={() => setFinishModalOpen(true)}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-60"
              >
                {submittedCount === totalChallenges && totalChallenges > 0
                  ? "Finish assessment"
                  : "Finish early"}
              </button>
            )}
          </div>
          {totalChallenges > 1 && (
            <ChallengeNavigator
              challenges={session.challenges}
              selectedId={selected?.challenge_id ?? session.challenges[0].challenge_id}
              onSelect={setSelectedId}
            />
          )}
          {!sessionLocked && submittedCount === totalChallenges && totalChallenges > 0 && (
            <p className="rounded-lg border border-success/30 bg-success/5 px-3 py-2 text-sm text-neutral">
              All challenges submitted. Finish the assessment to lock your answers and view final
              results.
            </p>
          )}
        </div>
      )}

      {step === "challenge" && session && selected && (
        <section className="space-y-4">
          {session.generation_notes && (
            <p className="rounded-lg bg-surface-muted px-4 py-2 text-sm text-neutral/80">
              {session.generation_notes}
            </p>
          )}
          <div className="rounded-lg border border-border bg-white p-4 text-sm">
            <p className="font-medium text-neutral">
              Challenge {selected.position} of {totalChallenges || selected.challenge_count}:{" "}
              {selected.title}
            </p>
            <p className="mt-1">
              <span className="font-medium">Language:</span> {selected.language} ·{" "}
              <span className="font-medium">Category:</span> {selected.category} ·{" "}
              <span className="font-medium">Difficulty:</span> {selected.difficulty} ·{" "}
              <span className="font-medium">Duration:</span> {selected.estimated_duration}
            </p>
            {selected.requirements.length > 0 && (
              <ul className="mt-2 list-inside list-disc text-neutral/80">
                {selected.requirements.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </div>
          {adaptiveStatus && (
            <p className="rounded-lg border border-border bg-surface-muted px-4 py-2 text-sm text-neutral">
              {adaptiveStatus}
            </p>
          )}
          <CodeTool
            key={selected.challenge_id}
            sessionId={session.session_id}
            challenge={selected}
            sessionRemainingSeconds={session.total_remaining_seconds}
            disabled={selected.submitted || session.status !== "active" || sessionLocked}
            blockClipboard
            adaptiveMode={adaptiveMode}
            onSubmitted={handleSubmitted}
            onAdaptiveSubmitted={handleAdaptiveSubmitted}
            onRunComplete={() => void refresh()}
          />
        </section>
      )}

      {step === "done" && (
        <section className="space-y-4 rounded-xl border border-border bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold">Assessment complete</h2>
          {completionSummary && (
            <div className="rounded-lg border border-success/30 bg-success/5 p-4 text-sm text-neutral">
              <p className="font-medium">{completionSummary.message}</p>
              <p className="mt-1 text-neutral/70">
                Submitted {completionSummary.challenges_submitted}/
                {completionSummary.challenges_total} challenges · Finished at{" "}
                {new Date(completionSummary.completed_at).toLocaleString()}
              </p>
            </div>
          )}
          {integrityReport && <IntegrityReportCard report={integrityReport} />}
          <SessionSummary
            submissions={allSubmissions}
            challengeTitles={Object.fromEntries(
              (session?.challenges ?? []).map((challenge) => [
                challenge.challenge_id,
                challenge.title,
              ]),
            )}
          />
          {!adaptiveMode && lastResult && <SubmissionResults result={lastResult} />}
          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="button"
              onClick={() => setStep("challenge")}
              disabled={!sessionLocked}
              className="rounded-lg border border-border px-4 py-2 text-sm font-semibold text-neutral hover:bg-surface-muted disabled:opacity-50"
            >
              Review challenges (read-only)
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("profile");
                setSessionId(null);
                setSession(null);
                setSelectedId(null);
                setLastResult(null);
                setAllSubmissions([]);
                setIntegrityReport(null);
                setCompletionSummary(null);
                setError(null);
              }}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white"
            >
              Start new session
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
