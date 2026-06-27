"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  analyzeAudioSignal,
  analyzeCameraFrame,
  getProctoringPolicy,
  getSessionIntegrity,
  recordProctoringEvent,
} from "@/features/proctoring/api";
import type {
  IntegrityMonitorState,
  ProctoringEventType,
  ProctoringPolicyResponse,
} from "@/features/proctoring/types";

const IDLE_MS = 120_000;
const AUDIO_POLL_MS = 5_000;
const INTEGRITY_POLL_MS = 30_000;
const DEVTOOLS_THRESHOLD = 160;
/** Camera VLM cadence ceiling (WP-4): default 1.5s, max 2s. */
const CAMERA_POLL_MS = Math.min(
  2000,
  Number(process.env.NEXT_PUBLIC_PROCTORING_CAMERA_INTERVAL_MS ?? 1500),
);

export interface UseProctoringOptions {
  sessionId: string;
  enabled?: boolean;
  /** Must be true before camera/microphone capture (consent gate). */
  consentGiven?: boolean;
  referenceImageB64?: string;
  onViolation?: (eventType: ProctoringEventType) => void;
  onFlagged?: () => void;
}

function isEnabled(
  policy: ProctoringPolicyResponse | null,
  eventType: ProctoringEventType,
): boolean {
  return policy?.enabled_checks.includes(eventType) ?? false;
}

function captureVideoFrame(video: HTMLVideoElement): string | null {
  if (video.videoWidth === 0 || video.videoHeight === 0) return null;
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
  return dataUrl.split(",")[1] ?? null;
}

export function useProctoring({
  sessionId,
  enabled = true,
  consentGiven = false,
  referenceImageB64,
  onViolation,
  onFlagged,
}: UseProctoringOptions) {
  const [policy, setPolicy] = useState<ProctoringPolicyResponse | null>(null);
  const [state, setState] = useState<IntegrityMonitorState>({
    active: false,
    violationCount: 0,
    highSeverityCount: 0,
    verificationStatus: null,
    lastViolation: null,
    cameraReady: false,
    microphoneReady: false,
    error: null,
  });

  const policyRef = useRef(policy);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const lastActivityRef = useRef(Date.now());
  const flaggedRef = useRef(false);
  const isAnalyzingCameraRef = useRef(false);

  policyRef.current = policy;

  const reportEvent = useCallback(
    async (eventType: ProctoringEventType, metadata?: Record<string, unknown>) => {
      if (!enabled || !policyRef.current) return;
      if (!isEnabled(policyRef.current, eventType)) return;

      try {
        await recordProctoringEvent({
          session_id: sessionId,
          event_type: eventType,
          metadata,
          client_timestamp: new Date().toISOString(),
        });
        setState((prev) => ({
          ...prev,
          violationCount: prev.violationCount + 1,
          lastViolation: eventType,
        }));
        onViolation?.(eventType);
      } catch (err) {
        const message = err instanceof Error ? err.message : "event failed";
        if (!message.includes("cooldown") && !message.includes("409")) {
          setState((prev) => ({ ...prev, error: message }));
        }
      }
    },
    [enabled, onViolation, sessionId],
  );

  const refreshIntegrity = useCallback(async () => {
    try {
      const summary = await getSessionIntegrity(sessionId);
      setState((prev) => ({
        ...prev,
        highSeverityCount: summary.high_severity_count,
        verificationStatus: summary.verification_status,
      }));
      if (
        summary.verification_status === "flagged" &&
        !flaggedRef.current
      ) {
        flaggedRef.current = true;
        onFlagged?.();
      }
    } catch {
      // integrity poll is best-effort
    }
  }, [onFlagged, sessionId]);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    (async () => {
      try {
        const loaded = await getProctoringPolicy(sessionId);
        if (!cancelled) {
          setPolicy(loaded);
          setState((prev) => ({ ...prev, active: true, error: null }));
        }
      } catch (err) {
        if (!cancelled) {
          setState((prev) => ({
            ...prev,
            error: err instanceof Error ? err.message : "policy load failed",
          }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled, sessionId]);

  useEffect(() => {
    if (!enabled || !policy) return;

    const touchActivity = () => {
      lastActivityRef.current = Date.now();
    };

    const onVisibility = () => {
      if (document.hidden) {
        void reportEvent("tab_switch", { source: "visibilitychange" });
      }
    };

    const onBlur = () => {
      void reportEvent("window_blur", { source: "window.blur" });
    };

    const onCopy = () => {
      void reportEvent("copy", { source: "clipboard" });
    };

    const onPaste = () => {
      void reportEvent("paste", { source: "clipboard" });
    };

    const onContextMenu = (event: MouseEvent) => {
      void reportEvent("context_menu", { x: event.clientX, y: event.clientY });
    };

    const onPrint = () => {
      void reportEvent("print_attempt", { source: "beforeprint" });
    };

    const onFullscreen = () => {
      if (!document.fullscreenElement) {
        void reportEvent("fullscreen_exit", { source: "fullscreenchange" });
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      touchActivity();
      if (event.key === "PrintScreen") {
        void reportEvent("screenshot", { source: "PrintScreen" });
      }
    };

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("copy", onCopy);
    document.addEventListener("paste", onPaste);
    document.addEventListener("contextmenu", onContextMenu);
    window.addEventListener("beforeprint", onPrint);
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousemove", touchActivity);
    document.addEventListener("mousedown", touchActivity);

    const devtoolsTimer = window.setInterval(() => {
      const gap = window.outerWidth - window.innerWidth;
      if (gap > DEVTOOLS_THRESHOLD) {
        void reportEvent("devtools_open", { gap });
      }
    }, 2_000);

    const idleTimer = window.setInterval(() => {
      if (Date.now() - lastActivityRef.current >= IDLE_MS) {
        void reportEvent("idle_timeout", { idle_ms: IDLE_MS });
        lastActivityRef.current = Date.now();
      }
    }, 15_000);

    const integrityTimer = window.setInterval(() => {
      void refreshIntegrity();
    }, INTEGRITY_POLL_MS);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("contextmenu", onContextMenu);
      window.removeEventListener("beforeprint", onPrint);
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousemove", touchActivity);
      document.removeEventListener("mousedown", touchActivity);
      window.clearInterval(devtoolsTimer);
      window.clearInterval(idleTimer);
      window.clearInterval(integrityTimer);
    };
  }, [enabled, policy, refreshIntegrity, reportEvent]);

  useEffect(() => {
    if (!enabled || !policy?.require_camera || !consentGiven) return;

    let cancelled = false;
    let cameraTimer: number | undefined;

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: 640, height: 480 },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        cameraStreamRef.current = stream;
        const video = document.createElement("video");
        video.srcObject = stream;
        video.muted = true;
        video.playsInline = true;
        await video.play();
        videoRef.current = video;
        setState((prev) => ({ ...prev, cameraReady: true }));

        const policyPollMs = policy.camera_poll_interval_seconds * 1000;
        const pollMs = Math.min(CAMERA_POLL_MS, policyPollMs);
        cameraTimer = window.setInterval(() => {
          if (isAnalyzingCameraRef.current) return;

          const frame = videoRef.current
            ? captureVideoFrame(videoRef.current)
            : null;
          if (!frame) return;

          isAnalyzingCameraRef.current = true;
          void analyzeCameraFrame({
            session_id: sessionId,
            frame_b64: frame,
            reference_image_b64: referenceImageB64,
            client_timestamp: new Date().toISOString(),
          })
            .then((result) => {
              if (!result.compliant) {
                setState((prev) => ({
                  ...prev,
                  violationCount:
                    prev.violationCount + result.events_recorded.length,
                  lastViolation:
                    result.violations[0]?.event_type ?? prev.lastViolation,
                }));
                for (const violation of result.violations) {
                  onViolation?.(violation.event_type);
                }
              }
              void refreshIntegrity();
            })
            .catch(() => {
              void reportEvent("camera_disabled", { source: "analyze-camera" });
            })
            .finally(() => {
              isAnalyzingCameraRef.current = false;
            });
        }, pollMs);
      } catch {
        void reportEvent("camera_disabled", { source: "getUserMedia" });
        setState((prev) => ({ ...prev, cameraReady: false }));
      }
    })();

    return () => {
      cancelled = true;
      if (cameraTimer) window.clearInterval(cameraTimer);
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
      videoRef.current = null;
    };
  }, [
    consentGiven,
    enabled,
    onViolation,
    policy,
    referenceImageB64,
    refreshIntegrity,
    reportEvent,
    sessionId,
  ]);

  useEffect(() => {
    if (!enabled || !policy?.require_microphone || !consentGiven) return;

    let cancelled = false;
    let audioTimer: number | undefined;

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        micStreamRef.current = stream;
        const audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        audioContextRef.current = audioContext;
        analyserRef.current = analyser;
        setState((prev) => ({ ...prev, microphoneReady: true }));

        const data = new Uint8Array(analyser.frequencyBinCount);
        audioTimer = window.setInterval(() => {
          const track = stream.getAudioTracks()[0];
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i += 1) {
            const normalized = (data[i] - 128) / 128;
            sum += normalized * normalized;
          }
          const rms = Math.sqrt(sum / data.length);

          void analyzeAudioSignal({
            session_id: sessionId,
            average_rms: rms,
            microphone_muted: track?.muted ?? false,
            microphone_enabled: track?.enabled ?? false,
            client_timestamp: new Date().toISOString(),
          })
            .then((result) => {
              if (!result.compliant) {
                setState((prev) => ({
                  ...prev,
                  violationCount:
                    prev.violationCount + result.events_recorded.length,
                  lastViolation:
                    result.violations[0]?.event_type ?? prev.lastViolation,
                }));
                for (const violation of result.violations) {
                  onViolation?.(violation.event_type);
                }
              }
            })
            .catch(() => {
              void reportEvent("microphone_disabled", {
                source: "analyze-audio",
              });
            });
        }, AUDIO_POLL_MS);
      } catch {
        void reportEvent("microphone_disabled", { source: "getUserMedia" });
        setState((prev) => ({ ...prev, microphoneReady: false }));
      }
    })();

    return () => {
      cancelled = true;
      if (audioTimer) window.clearInterval(audioTimer);
      micStreamRef.current?.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
      void audioContextRef.current?.close();
      audioContextRef.current = null;
      analyserRef.current = null;
    };
  }, [consentGiven, enabled, policy, reportEvent, sessionId]);

  return { policy, state, reportEvent, refreshIntegrity };
}
