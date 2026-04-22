import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpsBrain — AI-Native AIOps Platform",
  description: "Transparent AI-powered incident response, cost optimization, and Kubernetes management",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0f1117] text-slate-200 min-h-screen">{children}</body>
    </html>
  );
}
