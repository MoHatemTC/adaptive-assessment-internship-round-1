import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Masaar Assessment",
  description: "Adaptive assessment platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface text-neutral antialiased">
        {children}
      </body>
    </html>
  );
}
