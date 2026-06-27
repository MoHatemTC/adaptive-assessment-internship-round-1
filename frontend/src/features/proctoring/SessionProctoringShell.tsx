"use client";

import { IntegrityMonitor } from "./IntegrityMonitor";
import type { UseSessionProctoringOptions } from "./useSessionProctoring";

export interface SessionProctoringShellProps extends UseSessionProctoringOptions {
  children: React.ReactNode;
  showBadge?: boolean;
}

/** Assessment wrapper: platform session lifecycle + integrity monitoring. */
export function SessionProctoringShell({
  children,
  showBadge = true,
  manageLifecycle = true,
  ...options
}: SessionProctoringShellProps) {
  return (
    <IntegrityMonitor
      showBadge={showBadge}
      manageLifecycle={manageLifecycle}
      {...options}
    >
      {children}
    </IntegrityMonitor>
  );
}

export { useSessionProctoring } from "./useSessionProctoring";
export type { UseSessionProctoringOptions } from "./useSessionProctoring";
