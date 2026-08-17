import { ApiDownNotice, NoSnapshotNotice, Portfolio } from "@/components/ui";
import { ApiUnavailable, portfolio } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  let industries;
  try {
    industries = await portfolio();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const organisations = industries.flatMap((industry) => industry.organisations);
  if (organisations.length === 0) return <NoSnapshotNotice />;

  const graded = organisations.filter((org) => org.composite_score != null);
  const blocked = organisations.filter((org) => org.hard_blockers > 0);

  return (
    <>
      <div className="eyebrow">Executive view</div>
      <h1>Assessed organizations</h1>
      <p className="lede">
        {organisations.length} organizations across {industries.length} industries, each assessed on its
        own data estate and scored from its own machine evidence. Open one to read its blockers,
        benchmarks, roadmap, evidence and review queue — every organization has its own page.
      </p>
      <p className="muted" style={{ marginTop: "-0.5rem" }}>
        {graded.length} scored · {blocked.length} carrying at least one hard blocker · scores are
        composite readiness out of 100.
      </p>

      <Portfolio industries={industries} />
    </>
  );
}
