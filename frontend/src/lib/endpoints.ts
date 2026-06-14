/** API and WebSocket base URLs for browser clients. */

const DEFAULT_API = "http://localhost:8000";

export function getApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API;
}

/**
 * WebSocket base for the examiner session channel.
 * Always targets the FastAPI backend — never the Next.js dev server on :3000.
 */
export function getWebSocketBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  if (explicit) {
    return explicit.replace(/\/$/, "");
  }
  return getApiBaseUrl().replace(/^http/, "ws");
}

export function getSessionChannelWebSocketUrl(sessionId: string): string {
  const base = getWebSocketBaseUrl();
  return `${base}/api/v1/integrations/sessions/${encodeURIComponent(sessionId)}/ws`;
}
