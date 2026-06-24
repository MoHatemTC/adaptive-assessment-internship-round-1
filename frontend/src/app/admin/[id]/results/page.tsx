"use client";

import { Suspense } from "react";

import { AdminResultsClient } from "./AdminResultsClient";

export default function AdminResultsPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-4xl px-4 py-8 text-sm text-neutral/70">
          Loading results…
        </main>
      }
    >
      <AdminResultsClient />
    </Suspense>
  );
}
