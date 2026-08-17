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
      <h1>Assessed estates</h1>
      <p className="lede">
        {organisations.length} organisations across {industries.length} industries, each scored from
        its own machine evidence. Open an estate to read its blockers, benchmarks, roadmap, evidence
        and review queue — every estate has its own page.
      </p>
      <p className="muted" style={{ marginTop: "-0.5rem" }}>
        {graded.length} scored · {blocked.length} carrying at least one hard blocker · scores are
        composite readiness out of 100.
      </p>

      <Portfolio industries={industries} />
    </>
  );
}
