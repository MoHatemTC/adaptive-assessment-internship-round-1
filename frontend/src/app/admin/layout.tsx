"use client";

import { useCallback, useEffect, useState } from "react";

import {
  clearAdminToken,
  isAdminTokenValid,
} from "@/lib/admin-auth";
import { adminLogin, setAdminToken } from "@/lib/admin-api";

const SESSION_EXPIRED_MESSAGE = "Session expired — sign in again";

/**
 * Admin area layout with a lightweight auth gate. When no valid admin JWT is
 * present it shows a sign-in form; otherwise it renders the admin pages.
 */
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isAdminTokenValid()) {
      clearAdminToken();
      setAuthed(false);
      return;
    }
    setAuthed(true);
  }, []);

  useEffect(() => {
    const onSessionExpired = () => {
      clearAdminToken();
      setAuthed(false);
      setError(SESSION_EXPIRED_MESSAGE);
    };
    window.addEventListener("admin-session-expired", onSessionExpired);
    return () => {
      window.removeEventListener("admin-session-expired", onSessionExpired);
    };
  }, []);

  const handleLogin = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      setLoading(true);
      setError(null);
      try {
        const { access_token } = await adminLogin(username, password);
        setAdminToken(access_token);
        setAuthed(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Sign-in failed");
      } finally {
        setLoading(false);
      }
    },
    [username, password],
  );

  if (authed === null) {
    return null;
  }

  if (!authed) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center gap-5 px-4">
        <h1 className="text-2xl font-semibold text-[#1F2430]">Admin sign-in</h1>
        <form onSubmit={handleLogin} className="space-y-4">
          <label className="block text-sm text-[#1F2430]">
            <span className="mb-1 block font-medium">Username</span>
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-lg border border-[#D8DDF0] bg-white px-3 py-2"
              required
            />
          </label>
          <label className="block text-sm text-[#1F2430]">
            <span className="mb-1 block font-medium">Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg border border-[#D8DDF0] bg-white px-3 py-2"
              required
            />
          </label>
          {error && (
            <p className="rounded-lg border border-[#E5484D]/30 bg-[#E5484D]/5 p-3 text-sm text-[#E5484D]">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-[#004EFF] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#3374FF] disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </main>
    );
  }

  return <>{children}</>;
}
