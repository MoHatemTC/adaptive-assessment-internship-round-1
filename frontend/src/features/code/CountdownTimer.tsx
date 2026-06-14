"use client";

import { useEffect, useState } from "react";

function formatSeconds(total: number): string {
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export interface CountdownTimerProps {
  remainingSeconds: number;
  label?: string;
  onExpire?: () => void;
}

export function CountdownTimer({
  remainingSeconds,
  label = "Time remaining",
  onExpire,
}: CountdownTimerProps) {
  const [seconds, setSeconds] = useState(remainingSeconds);

  useEffect(() => {
    setSeconds(remainingSeconds);
  }, [remainingSeconds]);

  useEffect(() => {
    if (seconds <= 0) {
      onExpire?.();
      return;
    }
    const id = window.setInterval(() => {
      setSeconds((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => window.clearInterval(id);
  }, [seconds, onExpire]);

  const urgent = seconds <= 60;

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${
        urgent ? "bg-error/10 text-error" : "bg-primary-20 text-primary"
      }`}
      aria-live="polite"
    >
      <span className="text-xs font-medium uppercase tracking-wide opacity-80">{label}</span>
      <span>{formatSeconds(seconds)}</span>
    </div>
  );
}
