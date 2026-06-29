import { ADMIN_TOKEN_KEY } from "@/lib/admin-api";

/** Thrown when the admin JWT is missing, expired, or rejected by the API. */
export class SessionExpiredError extends Error {
  constructor(message = "Session expired — sign in again") {
    super(message);
    this.name = "SessionExpiredError";
  }
}

interface JwtPayload {
  exp?: number;
}

/** Decode a JWT payload without verifying the signature (client-side expiry check only). */
export function decodeJwtPayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const json = atob(padded);
    const payload = JSON.parse(json) as JwtPayload;
    return payload && typeof payload === "object" ? payload : null;
  } catch {
    return null;
  }
}

/** Whether the stored admin token exists and has not passed its ``exp`` claim. */
export function isAdminTokenValid(token?: string): boolean {
  const value =
    token ?? (typeof window !== "undefined" ? localStorage.getItem(ADMIN_TOKEN_KEY) : null);
  if (!value) return false;
  const payload = decodeJwtPayload(value);
  if (!payload?.exp) return false;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp > nowSeconds;
}

/** Remove the admin JWT from localStorage. */
export function clearAdminToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}
