import Link from "next/link";
import { EstateTabs } from "@/components/estate-tabs";
import { ApiDownNotice, Pill, UnknownEstateNotice, gradeColor } from "@/components/ui";
import { ApiUnavailable, findOrg } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * The frame every estate page shares: who this is, what it scored, and the
 * three role views for *this* estate. The snapshot lives in the path, so each
 * estate is a page of its own that can be linked, bookmarked and opened in a
 * new tab.
 */
export default async function EstateLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ snapshot: string }>;
}) {
  const { snapshot } = await params;

  let found;
  try {
    found = await findOrg(snapshot);
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }
  if (!found) return <UnknownEstateNotice snapshotId={snapshot} />;

  const { org, industry } = found;
  return (
    <>
      <div className="estate-head">
        <div>
          <div className="eyebrow">
            <Link href="/">Assessed estates</Link> · {industry.industry_label}
          </div>
          <h1 style={{ marginBottom: "0.3rem" }}>{org.tenant}</h1>
          <div className="estate-strip">
            <Pill label={org.grade ?? "unscored"} color={gradeColor(org.composite_score)} />
            <span className="muted">{org.grade_interpretation}</span>
            <span className="muted">{org.size_band.replace(/_/g, " ")}</span>
            <span className="muted mono">{org.snapshot_id}</span>
          </div>
        </div>
        <div className="estate-scores">
          <div className="estate-score">
            <strong style={{ color: gradeColor(org.composite_score) }}>
              {org.composite_score?.toFixed(1) ?? "--"}
            </strong>
            <span>composite</span>
          </div>
          <div className="estate-score">
            <strong style={{ color: gradeColor(org.ari_score) }}>
              {org.ari_score?.toFixed(1) ?? "--"}
            </strong>
            <span>Agent Readiness Index</span>
          </div>
          <div className="estate-score">
            <strong style={{ color: gradeColor(org.rri_score) }}>
              {org.rri_score?.toFixed(1) ?? "--"}
            </strong>
            <span>RAG Readiness Index</span>
          </div>
        </div>
      </div>

      <EstateTabs snapshotId={org.snapshot_id} />
      {children}
    </>
  );
}
