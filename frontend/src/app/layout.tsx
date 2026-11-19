import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { AccessGate } from "@/components/AccessGate";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "LLM File Analyzer",
  description: "Upload and analyze documents for LLM queries.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full flex" style={{ background: "var(--bg)", color: "var(--text)" }}>
        <Sidebar />
        <div className="flex-1 min-h-screen overflow-y-auto">
          <AccessGate>{children}</AccessGate>
        </div>
      </body>
    </html>
  );
}
