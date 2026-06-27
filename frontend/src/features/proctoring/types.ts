export type ProctoringEventType =
  | "tab_switch"
  | "window_blur"
  | "fullscreen_exit"
  | "devtools_open"
  | "context_menu"
  | "print_attempt"
  | "copy"
  | "paste"
  | "copy_paste"
  | "screenshot"
  | "ai_usage"
  | "idle_timeout"
  | "identity_fail"
  | "identity_verified"
  | "face_absent"
  | "multiple_faces"
  | "camera_obstructed"
  | "camera_disabled"
  | "looking_away"
  | "identity_mismatch"
  | "microphone_muted"
  | "microphone_disabled"
  | "audio_absent"
  | "session_started"
  | "session_stopped";

export type ProctoringSeverity = "low" | "medium" | "high";

export type VerificationStatus =
  | "pending"
  | "verified"
  | "flagged"
  | "identity_failed";

export interface ProctoringPolicy {
  high_severity_threshold: number;
  enabled_checks: ProctoringEventType[];
  camera_poll_interval_seconds: number;
  event_cooldown_seconds: number;
  require_camera: boolean;
  require_microphone: boolean;
}

export interface ProctoringPolicyResponse extends ProctoringPolicy {
  session_id: string;
  default_severities: Record<ProctoringEventType, ProctoringSeverity>;
}

export interface ProctoringEventCreate {
  session_id: string;
  event_type: ProctoringEventType;
  severity?: ProctoringSeverity;
  metadata?: Record<string, unknown>;
  client_timestamp?: string;
}

export interface ProctoringEventBatchCreate {
  session_id: string;
  events: ProctoringEventCreate[];
}

export interface ProctoringEventRead {
  id: number;
  session_id: string;
  event_type: ProctoringEventType;
  severity: ProctoringSeverity;
  metadata?: Record<string, unknown> | null;
  client_timestamp?: string | null;
  created_at: string;
}

export interface SessionIntegritySummary {
  session_id: string;
  verification_status: VerificationStatus;
  high_severity_count: number;
  threshold: number;
  identity_verified: boolean;
  events: ProctoringEventRead[];
}

export interface SessionIntegritySnapshot {
  verification_status: VerificationStatus;
  high_severity_count: number;
  threshold: number;
  identity_verified: boolean;
}

export interface IdentityVerifyResponse {
  verified: boolean;
  match_score: number | null;
  verification_status: VerificationStatus;
  message?: string;
}

export interface CameraAnalyzeResponse {
  compliant: boolean;
  face_visible: boolean;
  face_count: number;
  identity_match_score: number | null;
  violations: Array<{
    event_type: ProctoringEventType;
    severity: ProctoringSeverity;
    description: string;
  }>;
  events_recorded: ProctoringEventRead[];
}

export interface AudioAnalyzeResponse {
  compliant: boolean;
  violations: Array<{
    event_type: ProctoringEventType;
    severity: ProctoringSeverity;
    description: string;
  }>;
  events_recorded: ProctoringEventRead[];
}

export interface IntegrityMonitorState {
  active: boolean;
  violationCount: number;
  highSeverityCount: number;
  verificationStatus: VerificationStatus | null;
  lastViolation: ProctoringEventType | null;
  cameraReady: boolean;
  microphoneReady: boolean;
  error: string | null;
}
