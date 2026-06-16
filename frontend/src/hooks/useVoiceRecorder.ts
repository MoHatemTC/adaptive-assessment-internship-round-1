"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Lifecycle of a voice recording session. */
export type VoiceRecorderState = "idle" | "recording" | "completed";

/** A real-time transcript delta pushed by the backend over the WebSocket. */
interface TranscriptDeltaMessage {
  type: "transcript_delta";
  text: string;
  is_final: boolean;
}

/** Final message sent when the backend finalizes the session. */
interface SessionCompleteMessage {
  type: "session_complete";
  final_transcript: string;
}

type VoiceServerMessage = TranscriptDeltaMessage | SessionCompleteMessage;

interface UseVoiceRecorderOptions {
  /** Voice session id; path segment of the stream WebSocket URL. */
  voiceSessionId: string;
  /** Interview time limit in seconds; drives the countdown and auto-stop. */
  timeLimitSeconds: number;
  /** Base WebSocket URL of the stream endpoint (without the session segment). */
  wsUrl: string;
  /** Called once with the final transcript when the interview completes. */
  onComplete: (transcript: string) => void;
}

interface UseVoiceRecorderResult {
  /** Current lifecycle state. */
  state: VoiceRecorderState;
  /** Accumulated transcript text (live during recording, final when complete). */
  transcript: string;
  /** Seconds remaining before auto-stop. */
  remainingSeconds: number;
  /** Live analyser node for waveform rendering, or null when idle/stopped. */
  analyser: AnalyserNode | null;
  /** Most recent error message, or null. */
  error: string | null;
  /** Begin capturing microphone audio and streaming it to the backend. */
  start: () => Promise<void>;
  /** Stop capture, finalize the session, and transition to "completed". */
  stop: () => void;
}

/** Interval, in ms, at which MediaRecorder emits an audio chunk to stream. */
const CHUNK_TIMESLICE_MS = 250;

/**
 * Encapsulates microphone capture, WebSocket audio streaming, live
 * transcription, and the interview countdown for a single voice session.
 *
 * Audio is captured with the MediaRecorder API and streamed as binary frames
 * over a WebSocket to `${wsUrl}/${voiceSessionId}/stream`. Incoming
 * `transcript_delta` messages are appended to `transcript`; a `session_complete`
 * message (or a manual `stop`) finalizes the session, fires `onComplete`, and
 * moves to the `"completed"` state. An `AnalyserNode` is exposed so the UI can
 * draw a live waveform. The countdown auto-stops the interview at zero.
 *
 * All side effects are cleaned up on unmount.
 */
export function useVoiceRecorder({
  voiceSessionId,
  timeLimitSeconds,
  wsUrl,
  onComplete,
}: UseVoiceRecorderOptions): UseVoiceRecorderResult {
  const [state, setState] = useState<VoiceRecorderState>("idle");
  const [transcript, setTranscript] = useState<string>("");
  const [remainingSeconds, setRemainingSeconds] = useState<number>(timeLimitSeconds);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptRef = useRef<string>("");
  const completedRef = useRef<boolean>(false);

  // Keep the latest onComplete without re-binding the streaming callbacks.
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  /** Tear down media, socket, and timer resources. Safe to call repeatedly. */
  const teardown = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setAnalyser(null);
  }, []);

  /** Finalize exactly once: tear down, persist transcript, fire onComplete. */
  const finalize = useCallback(
    (finalTranscript: string) => {
      if (completedRef.current) {
        return;
      }
      completedRef.current = true;
      teardown();
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
      transcriptRef.current = finalTranscript;
      setTranscript(finalTranscript);
      setState("completed");
      onCompleteRef.current(finalTranscript);
    },
    [teardown],
  );

  const stop = useCallback(() => {
    finalize(transcriptRef.current);
  }, [finalize]);

  // Latest stop() for use inside timer/getUserMedia callbacks.
  const stopRef = useRef(stop);
  useEffect(() => {
    stopRef.current = stop;
  }, [stop]);

  const start = useCallback(async () => {
    if (state === "recording") {
      return;
    }
    setError(null);
    completedRef.current = false;
    transcriptRef.current = "";
    setTranscript("");
    setRemainingSeconds(timeLimitSeconds);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Web Audio analyser feeds the waveform visualizer.
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = 256;
      source.connect(analyserNode);
      setAnalyser(analyserNode);

      // Open the streaming socket and wire transcript handling.
      const socket = new WebSocket(`${wsUrl}/${voiceSessionId}/stream`);
      socket.binaryType = "arraybuffer";
      wsRef.current = socket;

      socket.onmessage = (event: MessageEvent) => {
        let message: VoiceServerMessage;
        try {
          message = JSON.parse(event.data as string) as VoiceServerMessage;
        } catch {
          return;
        }
        if (message.type === "transcript_delta") {
          if (message.text) {
            transcriptRef.current = transcriptRef.current
              ? `${transcriptRef.current} ${message.text}`
              : message.text;
            setTranscript(transcriptRef.current);
          }
        } else if (message.type === "session_complete") {
          finalize(message.final_transcript || transcriptRef.current);
        }
      };

      socket.onerror = () => {
        setError("Connection error during streaming.");
      };

      // Stream audio chunks as they are produced.
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
          socket.send(event.data);
        }
      };
      recorder.start(CHUNK_TIMESLICE_MS);

      setState("recording");

      // Countdown; auto-stop at zero.
      timerRef.current = setInterval(() => {
        setRemainingSeconds((prev) => {
          if (prev <= 1) {
            stopRef.current();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    } catch {
      teardown();
      setError("Microphone access was denied or is unavailable.");
    }
  }, [state, timeLimitSeconds, wsUrl, voiceSessionId, finalize, teardown]);

  // Clean up if the component unmounts mid-recording.
  useEffect(() => {
    return () => {
      teardown();
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    };
  }, [teardown]);

  return { state, transcript, remainingSeconds, analyser, error, start, stop };
}
