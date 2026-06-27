export const SESSION_TOKEN_KEY = "masaar_session_token";
export const SESSION_ID_KEY = "masaar_session_id";
export const IDENTITY_REFERENCE_KEY = "masaar_identity_reference_b64";

export function readIdentityReference(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(IDENTITY_REFERENCE_KEY);
}

export function persistSessionAuth(sessionId: string, accessToken: string): void {
  sessionStorage.setItem(SESSION_ID_KEY, sessionId);
  sessionStorage.setItem(SESSION_TOKEN_KEY, accessToken);
}

export function readSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(SESSION_ID_KEY);
}

export function readSessionAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(SESSION_TOKEN_KEY);
}

export function persistIdentityReference(referenceB64: string): void {
  sessionStorage.setItem(IDENTITY_REFERENCE_KEY, referenceB64);
}
