import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: { default: "LeadRank", template: "%s · LeadRank" },
  description: "Rank, explain and triage a scraped lead list before you spend a credit on it.",
};

export const viewport: Viewport = {
  themeColor: "#0E1420",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="min-h-screen bg-surface-0 font-sans antialiased">
        <NavBar />
        {children}
      </body>
    </html>
  );
}
