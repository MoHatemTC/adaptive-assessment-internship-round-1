"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { verifySessionIdentity } from "@/features/proctoring/api";
import { signInSession, startSession } from "@/lib/session-api";
import {
  persistIdentityReference,
  persistSessionAuth,
} from "@/lib/session-storage";

export interface AssessmentVerifyClientProps {
  assessmentId: string;
}

function captureVideoFrame(video: HTMLVideoElement): string | null {
  if (video.videoWidth === 0 || video.videoHeight === 0) return null;
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0);
  return canvas.toDataURL("image/jpeg", 0.7).split(",")[1] ?? null;
}

export function AssessmentVerifyClient({
  assessmentId,
}: AssessmentVerifyClientProps) {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [cvFile, setCvFile] = useState<File | undefined>();
  const [cameraReady, setCameraReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraReady(false);
  }, []);

  useEffect(() => () => stopCamera(), [stopCamera]);

  const enableCamera = useCallback(async () => {
    if (!consent) {
      setError("Consent is required before enabling the camera.");
      return;
    }
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: 640, height: 480 },
        audio: false,
      });
      streamRef.current = stream;
      const video = videoRef.current;
      if (video) {
        video.srcObject = stream;
        video.muted = true;
        video.playsInline = true;
        await video.play();
      }
      setCameraReady(true);
    } catch {
      setError("Camera permission is required for this assessment.");
    }
  }, [consent]);

  const handleContinue = useCallback(async () => {
    if (!consent) {
      setError("You must accept monitoring before continuing.");
      return;
    }
    const video = videoRef.current;
    const frame = video ? captureVideoFrame(video) : null;
    if (!frame) {
      setError("Enable the camera and wait for the preview before continuing.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const signIn = await signInSession(
        assessmentId,
        {
          name: name.trim() || "Learner",
          consent_given: true,
        },
        cvFile,
      );

      const verification = await verifySessionIdentity({
        session_id: signIn.session_id,
        reference_image_b64: frame,
        live_capture_b64: frame,
      });

      if (!verification.verified) {
        throw new Error(
          verification.message ?? "Identity verification failed. Try again in better lighting.",
        );
      }

      await startSession(signIn.session_id, signIn.access_token);
      persistSessionAuth(signIn.session_id, signIn.access_token);
      persistIdentityReference(frame);
      stopCamera();

      router.push(
        `/assessment/${assessmentId}/chat?session_id=${encodeURIComponent(signIn.session_id)}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
      setLoading(false);
    }
  }, [assessmentId, consent, name, cvFile, router, stopCamera]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center gap-6 px-4 py-8">
      <h1 className="text-2xl font-semibold text-neutral">Pre-assessment checks</h1>

      <div className="rounded-xl border border-border bg-surface-muted p-5 text-sm text-neutral/80">
        <p className="mb-3">
          Camera monitoring, tab-focus, and copy/paste detection run during this
          assessment. Your webcam stays on and frames are analyzed periodically
          for integrity (VLM). Nothing is stored except integrity event metadata.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Allow camera access when prompted.</li>
          <li>Stay on this tab; avoid external AI tools.</li>
          <li>Identity is verified once at session start.</li>
        </ul>
      </div>

      <label className="flex items-start gap-3 text-sm text-neutral">
        <input
          type="checkbox"
          className="mt-1"
          checked={consent}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <span>
          I consent to proctoring (camera monitoring, integrity event logging,
          and automated review) for this assessment.
        </span>
      </label>

      <label className="block text-sm text-neutral">
        <span className="mb-1 block font-medium">Your name (optional)</span>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="w-full rounded-lg border border-border bg-white px-3 py-2"
          placeholder="Learner name"
        />
      </label>

      <label className="block text-sm text-neutral">
        <span className="mb-1 block font-medium">Upload your CV (optional)</span>
        <input
          type="file"
          accept=".pdf"
          onChange={(event) => setCvFile(event.target.files?.[0])}
          className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm"
        />
        <span className="mt-1 block text-xs text-neutral/60">
          Your CV helps us personalize the assessment
        </span>
      </label>

      <div className="space-y-3">
        <video
          ref={videoRef}
          className={`aspect-video w-full max-w-sm rounded-lg border border-border bg-black object-cover ${cameraReady ? "block" : "hidden"}`}
        />
        {!cameraReady && (
          <button
            type="button"
            onClick={() => void enableCamera()}
            disabled={!consent || loading}
            className="rounded-lg border border-border bg-white px-4 py-2 text-sm font-medium text-neutral hover:bg-surface-muted disabled:opacity-50"
          >
            Enable camera
          </button>
        )}
      </div>

      {error && (
        <p className="rounded-lg border border-error/30 bg-error/5 p-3 text-sm text-error">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void handleContinue()}
          disabled={loading || !consent}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-60 disabled:opacity-50"
        >
          {loading ? "Verifying…" : "Verify identity & continue"}
        </button>
      </div>
    </main>
  );
}
