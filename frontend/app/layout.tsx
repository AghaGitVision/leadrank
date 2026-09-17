import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "LeadRank",
  description: "Rank, explain and triage a scraped lead list before you spend a credit on it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface-0 font-sans antialiased">
        <NavBar />
        {children}
      </body>
    </html>
  );
}
