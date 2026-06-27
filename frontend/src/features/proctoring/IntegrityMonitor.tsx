"use client";

import type { ReactNode } from "react";

import {
  useSessionProctoring,
  type UseSessionProctoringOptions,
} from "@/features/proctoring/useSessionProctoring";

export interface IntegrityMonitorProps extends UseSessionProctoringOptions {
  children?: ReactNode;
  showBadge?: boolean;
}

export function IntegrityMonitor({
  children,
  showBadge = true,
  ...options
}: IntegrityMonitorProps) {
  const { state } = useSessionProctoring(options);

  return (
    <>
      {children}
      {showBadge && options.enabled !== false && state.active && (
        <div
          className="fixed bottom-4 right-4 z-50 flex max-w-xs flex-col gap-1 rounded-lg border border-border bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur"
          aria-live="polite"
        >
          <span className="font-semibold text-neutral">Integrity monitor</span>
          <span className="text-neutral/70">
            {state.cameraReady ? "Camera on" : "Camera off"}
            {" · "}
            {state.microphoneReady ? "Mic on" : "Mic off"}
          </span>
          {state.verificationStatus && (
            <span className="capitalize text-neutral/80">
              Status: {state.verificationStatus.replace("_", " ")}
            </span>
          )}
          {state.lastViolation && (
            <span className="text-error">
              Last: {state.lastViolation.replace(/_/g, " ")}
            </span>
          )}
          {state.error && (
            <span className="text-error">{state.error}</span>
          )}
        </div>
      )}
    </>
  );
}
