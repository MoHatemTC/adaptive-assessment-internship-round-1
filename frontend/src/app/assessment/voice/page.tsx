"use client";

import { useMemo, useState } from "react";

import AdaptiveVoiceSession from "@/features/voice/AdaptiveVoiceSession";
import { PlatformSessionProctoring } from "@/features/proctoring/PlatformSessionProctoring";
import { resolvePlatformSessionId } from "@/lib/platform-session";

export default function VoiceAssessmentPage() {
  const [completed, setCompleted] = useState(false);
  const sessionId = useMemo(() => resolvePlatformSessionId("demo-session-001"), []);

  if (completed) {
    return (
      <div className="min-h-screen bg-[#FBFBFD] flex items-center justify-center">
        <div className="text-center">
          <p className="text-xl font-semibold text-[#1F2430]">
            Session Complete
          </p>
          <button
            onClick={() => setCompleted(false)}
            className="mt-4 bg-[#004EFF] text-white rounded-lg px-4 py-2 text-sm hover:bg-[#3374FF] transition"
          >
            Start New Session
          </button>
        </div>
      </div>
    );
  }

  return (
    <PlatformSessionProctoring>
    <AdaptiveVoiceSession
      sessionId={sessionId}
      initialQuestion="Tell me about a recent technical challenge you faced and how you solved it."
      initialDifficulty="beginner"
      timeLimitSeconds={120}
      learnerProfile={{
        name: "Demo Learner",
        role: "software_developer",
        level: "mid",
      }}
      adminConfig={{
        max_difficulty: "advanced",
        allowed_topics: ["problem_solving", "system_design", "debugging"],
      }}
      onComplete={() => setCompleted(true)}
    />
    </PlatformSessionProctoring>
  );
}
