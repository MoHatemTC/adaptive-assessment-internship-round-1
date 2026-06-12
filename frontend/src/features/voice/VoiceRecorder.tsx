"use client";

import { useEffect, useRef } from "react";

import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";

interface VoiceRecorderProps {
  /** Voice session id, used to build the stream WebSocket URL. */
  voiceSessionId: string;
  /** Interview time limit in seconds; drives the countdown and auto-stop. */
  timeLimitSeconds: number;
  /** Called with the final transcript when the interview completes. */
  onComplete: (transcript: string) => void;
  /** Base WebSocket URL of the stream endpoint (without the session segment). */
  wsUrl: string;
}

/** Format a number of seconds as `m:ss`. */
function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Time-boxed voice interview recorder with three states: idle, recording, and
 * completed.
 *
 * All capture, streaming, transcription, and timing live in the
 * `useVoiceRecorder` hook; this component is presentational. While recording it
 * paints a live waveform from the hook's `AnalyserNode`, shows a countdown, a
 * stop control, and a live transcript preview. On completion it renders the
 * final transcript.
 */
export default function VoiceRecorder({
  voiceSessionId,
  timeLimitSeconds,
  onComplete,
  wsUrl,
}: VoiceRecorderProps) {
  const { state, transcript, remainingSeconds, analyser, error, start, stop } =
    useVoiceRecorder({ voiceSessionId, timeLimitSeconds, wsUrl, onComplete });

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Draw the live waveform from the analyser while recording.
  useEffect(() => {
    if (state !== "recording" || !analyser || !canvasRef.current) {
      return;
    }
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    let frameId = 0;

    const draw = () => {
      frameId = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#004EFF";
      ctx.beginPath();

      const sliceWidth = canvas.width / bufferLength;
      let x = 0;
      for (let i = 0; i < bufferLength; i += 1) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
        x += sliceWidth;
      }
      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };

    draw();
    return () => cancelAnimationFrame(frameId);
  }, [state, analyser]);

  return (
    <section className="w-full max-w-2xl rounded-[24px] border border-[#D8DDF0] bg-[#FBFBFD] p-6 font-[family-name:var(--font-jakarta)] shadow-sm">
      {error ? (
        <p className="mb-4 rounded-lg bg-[#FDECEC] px-4 py-2 text-sm font-semibold text-[#E5484D]">
          {error}
        </p>
      ) : null}

      {state === "idle" ? (
        <div className="flex flex-col items-center gap-6 py-6">
          <h2 className="text-[21px] font-semibold leading-[25px] text-[#1F2430]">
            Voice Interview
          </h2>
          <p className="text-center text-base leading-6 text-[#343434]">
            You will have {formatTime(timeLimitSeconds)} to answer. Click the
            microphone to begin.
          </p>
          <button
            type="button"
            onClick={() => void start()}
            aria-label="Start recording"
            className="flex h-20 w-20 items-center justify-center rounded-full bg-[#004EFF] text-[#FBFBFD] transition hover:bg-[#3374FF]"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="h-8 w-8"
            >
              <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" />
              <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.92V21a1 1 0 1 0 2 0v-3.08A7 7 0 0 0 19 11Z" />
            </svg>
          </button>
        </div>
      ) : null}

      {state === "recording" ? (
        <div className="flex flex-col gap-5">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm font-semibold leading-[18px] text-[#004EFF]">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[#E5484D]" />
              Recording
            </span>
            <span className="text-[21px] font-semibold leading-[25px] tabular-nums text-[#1F2430]">
              {formatTime(remainingSeconds)}
            </span>
          </div>

          <canvas
            ref={canvasRef}
            width={560}
            height={96}
            className="h-24 w-full rounded-[24px] bg-[#E6EEFF]"
          />

          <div className="min-h-[72px] rounded-[24px] bg-[#FBFBFD] p-4 ring-1 ring-[#D8DDF0]">
            <p className="text-base leading-6 text-[#343434]">
              {transcript || (
                <span className="text-[#343434]/50">Listening…</span>
              )}
            </p>
          </div>

          <button
            type="button"
            onClick={stop}
            className="h-[43px] self-center rounded-lg bg-[#004EFF] px-6 py-3 text-sm font-semibold text-[#FBFBFD] transition hover:bg-[#3374FF]"
          >
            Stop &amp; Finish
          </button>
        </div>
      ) : null}

      {state === "completed" ? (
        <div className="flex flex-col gap-4">
          <h2 className="text-[21px] font-semibold leading-[25px] text-[#1F2430]">
            Interview Complete
          </h2>
          <div className="rounded-[24px] bg-[#E6EEFF] p-4">
            <p className="whitespace-pre-wrap text-base leading-6 text-[#343434]">
              {transcript || "No transcript was captured."}
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
