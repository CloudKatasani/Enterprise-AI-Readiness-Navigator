import Link from "next/link";
import { ApiDownNotice } from "@/components/ui";
import { DemoConsole } from "@/components/demo-console";
import { ApiUnavailable, demoOptions } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DemoPage() {
  let options;
  try {
    options = await demoOptions();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  return (
    <>
      <div className="eyebrow">Live demo</div>
      <h1>Assess an estate shaped like yours</h1>
      <p className="lede">
        Choose the platform, governance and quality tooling you actually run, say how far your
        governance programme has got, and press the button. EAIRN generates a synthetic estate to
        that shape and puts it through the same pipeline a real harvest goes through — 53 checks,
        rubric v{"2.0"}, hard-blocker caps, peer benchmarks, a simulated roadmap and a frozen,
        verifiable snapshot. You land on the executive view, with the action plan for your architects
        and stewards alongside it.
      </p>

      <div className="banner banner-info">
        <h3>Everything generated here is synthetic</h3>
        <p style={{ margin: 0 }}>
          No customer system is contacted, no credential is read, and no row of data exists to be
          read. The estate is generated locally from your choices and a seed, so the same
          configuration reproduces the same result exactly. What changes in a real assessment is the
          connector — a read-only harvest of your own catalog — and nothing else in the calculation.
          The narrative on the result is{" "}
          {options.advisor === "model"
            ? "written by Claude, grounded strictly in this snapshot's evidence"
            : "generated from a template, because no model API key is configured on this instance"}
          .
        </p>
      </div>

      <DemoConsole options={options} />

      <h2>What you will get</h2>
      <section className="grid cols-3">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Executive view</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            Composite grade with the Agent and RAG Readiness Indices, peer percentile with its cohort
            definition, the hard blockers that cap the score, top risks, and a costed roadmap whose
            impact was measured by re-running the scoring engine.
          </p>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Action plan</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            What to fix first, split by who owns it: architect items ranked by what closing them is
            worth, steward items for the review and findings queues, and the exact objects that fail
            each check.
          </p>
        </div>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Evidence, all the way down</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            Every number resolves to the check, measurement, confidence and rationale that produced
            it — see <Link href="/methodology">Methodology</Link> for the arithmetic and{" "}
            <Link href="/pillars">Scoring Pillars</Link> for why each pillar is there.
          </p>
        </div>
      </section>
    </>
  );
}
