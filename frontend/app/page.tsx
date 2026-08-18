import Link from "next/link";
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
      <section className="intro">
        <h2>Is this data estate actually ready for AI — and what gets fixed first?</h2>
        <p>
          EAIRN answers that with evidence instead of opinion. It reads <strong>metadata only</strong>
          {" "}— catalog, governance, lineage, quality, security and the AI surface itself; never a row
          of customer data — runs 53 automated checks, and scores eight pillars against a versioned
          rubric. Every number resolves to the check, measurement and failing objects behind it, and
          the remediation roadmap is ordered by impact <em>measured</em> by re-running the scoring
          engine, not estimated.
        </p>

        <h3>Why an organization should run this exercise before scaling AI</h3>
        <div className="why-grid">
          <div>
            <strong>Pilots fail on foundations, not models</strong>
            <p>
              Undocumented columns, unowned datasets and unmonitored pipelines surface as wrong
              answers in production — after the budget is committed. Measuring first turns that into
              a work list.
            </p>
          </div>
          <div>
            <strong>Some gaps are binary, not gradual</strong>
            <p>
              Classified data with no protection, or agent actions that cannot be attributed, cap what
              is safe to deploy however good the model is — {blocked.length} of the{" "}
              {organisations.length} estates assessed on this instance carry at least one.
            </p>
          </div>
          <div>
            <strong>&quot;Are we ready?&quot; needs an answer with a number</strong>
            <p>
              Without evidence the question is settled by whoever is most confident. A composite grade
              with a peer percentile and a named cohort gives a board something it can act on.
            </p>
          </div>
          <div>
            <strong>Readiness is a programme, not a verdict</strong>
            <p>
              Each run is an immutable, verifiable snapshot, so the same measurement repeated next
              quarter shows movement — and gives architects and stewards their own action lists in the
              meantime.
            </p>
          </div>
        </div>

        <p className="muted" style={{ marginBottom: 0 }}>
          New here? <Link href="/pillars">Scoring Pillars</Link> explains what each pillar asks and
          what skipping it costs · <Link href="/methodology">Methodology</Link> works the whole
          calculation through one estate · <Link href="/demo">Live Demo</Link> assesses an estate
          shaped like yours in about a second.
        </p>
      </section>

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
