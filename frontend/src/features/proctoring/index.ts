export { IntegrityMonitor } from "@/features/proctoring/IntegrityMonitor";
export type { IntegrityMonitorProps } from "@/features/proctoring/IntegrityMonitor";
export {
  analyzeAudioSignal,
  analyzeCameraFrame,
  getProctoringPolicy,
  getSessionIntegrity,
  recordProctoringEvent,
  recordProctoringEventsBatch,
} from "@/features/proctoring/api";
export { useProctoring } from "@/features/proctoring/useProctoring";
export type { UseProctoringOptions } from "@/features/proctoring/useProctoring";
export {
  SessionProctoringShell,
  useSessionProctoring,
} from "@/features/proctoring/SessionProctoringShell";
export type {
  SessionProctoringShellProps,
  UseSessionProctoringOptions,
} from "@/features/proctoring/SessionProctoringShell";
export { PlatformSessionProctoring } from "@/features/proctoring/PlatformSessionProctoring";
export type * from "@/features/proctoring/types";
