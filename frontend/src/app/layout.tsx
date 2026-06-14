import type { Metadata } from "next";

import { HealthStatus } from "@/components/HealthStatus";

import "./globals.css";

export const metadata: Metadata = {
  title: "Masaar Assessment",
  description: "AI adaptive assessment platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-border bg-white">
          <nav className="mx-auto flex max-w-4xl items-center gap-6 px-6 py-3 text-sm">
            <a href="/" className="font-semibold text-primary">
              Assessment
            </a>
            <a href="/assessment" className="text-neutral/70 hover:text-neutral">
              Agent
            </a>
            <a href="/code-demo" className="text-neutral/70 hover:text-neutral">
              Code demo
            </a>
            <a href="/admin" className="text-neutral/70 hover:text-neutral">
              Admin
            </a>
            <a href="/admin/integrity" className="text-neutral/70 hover:text-neutral">
              Integrity
            </a>
            <HealthStatus />
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
