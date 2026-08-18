import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "EAIRN — Enterprise AI Readiness Navigator",
  description:
    "Evidence-backed, vendor-neutral AI readiness scoring, benchmarking and remediation planning for enterprise data estates.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="masthead">
          <div className="masthead-inner">
            <Link href="/" className="wordmark" style={{ color: "#fff" }}>
              EAIRN
              <span>Enterprise AI Readiness Navigator</span>
            </Link>
            <nav className="roles">
              <Link href="/">Organizations</Link>
              <Link href="/architect">Architect</Link>
              <Link href="/steward">Steward</Link>
              <Link href="/demo">Live Demo</Link>
              <Link href="/connectors">Connectors</Link>
              <Link href="/api-docs">API Documentation</Link>
              <Link href="/data-model">Data Model</Link>
              <Link href="/pillars">Scoring Pillars</Link>
              <Link href="/methodology">Methodology</Link>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="site">
          Every number on these views is traceable to the evidence records that produced it.
          Assessments are immutable snapshots keyed by rubric version, evidence set and scores.
        </footer>
      </body>
    </html>
  );
}
