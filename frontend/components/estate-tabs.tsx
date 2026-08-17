"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { segment: "", label: "Executive", hint: "Score, blockers, roadmap" },
  { segment: "architect", label: "Architect", hint: "Heatmaps and evidence" },
  { segment: "steward", label: "Steward", hint: "Review and findings queue" },
] as const;

/**
 * Role tabs within one estate. Every tab keeps the snapshot in the path, so a
 * reader never lands on another organisation's numbers by switching role.
 */
export function EstateTabs({ snapshotId }: { snapshotId: string }) {
  const base = `/estates/${snapshotId}`;
  const pathname = usePathname();
  return (
    <nav className="estate-tabs" aria-label="Estate views">
      {TABS.map((tab) => {
        const href = tab.segment ? `${base}/${tab.segment}` : base;
        return (
          <Link key={tab.label} href={href} aria-current={pathname === href} title={tab.hint}>
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
