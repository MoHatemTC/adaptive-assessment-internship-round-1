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
export type * from "@/features/proctoring/types";
