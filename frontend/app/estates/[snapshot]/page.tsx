import Link from "next/link";
import {
  ApiDownNotice,
  BenchmarkRow,
  CapBanner,
  Dial,
  EvidenceItem,
  Metric,
  PillarBar,
} from "@/components/ui";
import { ApiUnavailable, executiveView } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function EstateExecutivePage({
  params,
  searchParams,
}: {
  params: Promise<{ snapshot: string }>;
  searchParams: Promise<{ from?: string }>;
}) {
  const { snapshot } = await params;
  const fromDemo = (await searchParams).from === "demo";

  let view;
  try {
    view = await executiveView(snapshot);
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const { assessment, investment } = view;
  const benchmarkByKey = new Map(view.benchmarks.map((b) => [b.metric_key, b]));
  const composite = benchmarkByKey.get("composite");
  const previous = view.trend.length > 1 ? view.trend[view.trend.length - 2] : null;
  const delta =
    previous?.composite_score != null && assessment.composite_score != null
      ? assessment.composite_score - previous.composite_score
      : null;

  const demoConfig = view.assessment.connectors?.[0]?.stats?.config ?? {};

  return (
    <>
      {fromDemo ? (
        <div className="banner banner-info">
          <h3>Evaluation complete</h3>
          <p style={{ margin: "0 0 0.4rem" }}>
            {view.assessment.tenant} scored{" "}
            <strong>{assessment.composite_score?.toFixed(1)}</strong> — {assessment.grade}. Everything
            below was produced by the run you just triggered: {assessment.stats?.evidence_records}{" "}
            evidence records across {assessment.stats?.datasets} datasets, scored under rubric v
            {assessment.rubric_version} and frozen as a verifiable snapshot.{" "}
            <Link href={`/estates/${snapshot}/actions`}>
              Open the action plan for your architects and stewards →
            </Link>
          </p>
          <div className="muted mono" style={{ fontSize: "0.78rem" }}>
            {demoConfig.platform} · governance {demoConfig.governance_tool} · quality{" "}
            {demoConfig.dq_tool} · maturity {demoConfig.maturity} · seed {demoConfig.seed}
            {demoConfig.scopes_excluded?.length
              ? ` · scope excluded: ${demoConfig.scopes_excluded.join(", ")}`
              : ""}
            {" · "}
            <Link href="/demo">run another</Link>
          </div>
        </div>
      ) : null}

      <div className="eyebrow">Executive view</div>
      <p className="lede">
        Scored from this estate&apos;s own machine evidence under rubric v{assessment.rubric_version}
        . {view.grade_interpretation}
      </p>

      <section className="card score-hero">
        <Dial value={assessment.composite_score} grade={assessment.grade} caption="composite" />
        <div className="grid cols-4" style={{ flex: 1, minWidth: "320px" }}>
          <Metric
            label="Agent Readiness Index"
            value={assessment.ari_score?.toFixed(1) ?? "--"}
            sub={assessment.ari_grade ?? "not scored"}
          />
          <Metric
            label="RAG Readiness Index"
            value={assessment.rri_score?.toFixed(1) ?? "--"}
            sub={assessment.rri_grade ?? "not scored"}
          />
          <Metric
            label="Peer percentile"
            value={composite ? `p${composite.percentile.toFixed(0)}` : "n/a"}
            sub={
              composite
                ? `${view.industry_label ?? composite.cohort_definition.industry}, n=${composite.cohort_definition.n}`
                : "no cohort"
            }
          />
          <Metric
            label="Trend vs prior"
            value={delta == null ? "first run" : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}`}
            sub={previous ? `from ${previous.composite_score?.toFixed(1)}` : "no prior snapshot"}
          />
        </div>
      </section>

      {view.caps_applied.length > 0 ? (
        <>
          <h2>Hard blockers</h2>
          <p className="lede">
            These caps bound the score regardless of progress elsewhere. Clearing them is the
            shortest path to a higher grade.
          </p>
          {view.caps_applied.map((cap) => (
            <CapBanner key={`${cap.override}-${cap.scope}`} cap={cap} />
          ))}
        </>
      ) : null}

      <h2>Pillar scores</h2>
      <section className="card">
        {view.pillars.map((pillar) => (
          <PillarBar key={pillar.key} score={pillar} benchmark={benchmarkByKey.get(pillar.key)} />
        ))}
        {view.indices.map((index) => (
          <PillarBar key={index.key} score={index} benchmark={benchmarkByKey.get(index.key)} />
        ))}
      </section>

      {view.advisor_narrative ? (
        <>
          <h2>Advisor narrative</h2>
          <section className="card">
            <div className="narrative">
              {view.advisor_narrative.body.split("\n\n").map((paragraph, index) => (
                <p key={index}>{paragraph}</p>
              ))}
            </div>
            <div className="muted mono" style={{ marginTop: "0.9rem" }}>
              generator {view.advisor_narrative.generator}
              {view.advisor_narrative.model ? ` (${view.advisor_narrative.model})` : ""} · confidence{" "}
              {view.advisor_narrative.confidence.toFixed(2)} · status {view.advisor_narrative.status}{" "}
              · {view.advisor_narrative.citations.length} evidence citation(s)
            </div>
            {view.advisor_narrative.cited_evidence.map((record) => (
              <EvidenceItem key={record.id} record={record} />
            ))}
          </section>
        </>
      ) : null}

      <h2>Top risks</h2>
      <section className="card">
        {view.top_risks.map((record) => (
          <EvidenceItem key={record.id} record={record} />
        ))}
      </section>

      <h2>Remediation roadmap</h2>
      <p className="lede">
        Sequenced by simulated composite impact per effort day. Impact is measured by re-running the
        scoring engine with each play&apos;s target applied — not estimated by hand.
      </p>
      <section className="grid cols-3" style={{ marginBottom: "1.1rem" }}>
        <Metric label="Total effort" value={`${investment.total_effort_days.toFixed(0)} days`} />
        <Metric
          label="Indicative cost"
          value={`$${investment.total_cost_estimate.toLocaleString()}`}
          sub="at the playbook day rate"
        />
        <Metric
          label="Projected composite"
          value={investment.projected_composite.toFixed(1)}
          sub={`from ${assessment.composite_score?.toFixed(1)} today`}
        />
      </section>

      {view.roadmap.map((horizon) => (
        <section className="card" key={horizon.horizon} style={{ marginBottom: "1rem" }}>
          <h3>
            {horizon.label} · {horizon.recommendations.length} play(s) ·{" "}
            {horizon.effort_days.toFixed(0)} days · projected{" "}
            {horizon.projected_impact >= 0 ? "+" : ""}
            {horizon.projected_impact.toFixed(1)} composite
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Play</th>
                  <th>Pillar</th>
                  <th>Effort</th>
                  <th>Composite impact</th>
                  <th>Unblocks</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {horizon.recommendations.map((rec) => (
                  <tr key={rec.id}>
                    <td>
                      <strong>{rec.title}</strong>
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        {rec.summary}
                      </div>
                    </td>
                    <td className="muted">{rec.pillar_key}</td>
                    <td className="num">{rec.effort_days.toFixed(0)}d</td>
                    <td className="num">
                      {rec.composite_impact >= 0 ? "+" : ""}
                      {rec.composite_impact.toFixed(2)}
                    </td>
                    <td className="muted">{rec.unblocks.join(", ") || "--"}</td>
                    <td className="muted">{rec.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <h2>Peer benchmarks</h2>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Score</th>
              <th>Percentile</th>
              <th>Cohort p25/p50/p75/p90</th>
              <th>Cohort definition</th>
            </tr>
          </thead>
          <tbody>
            {view.benchmarks.map((benchmark) => (
              <BenchmarkRow key={benchmark.metric_key} benchmark={benchmark} />
            ))}
          </tbody>
        </table>
      </section>

      <h2>Snapshot</h2>
      <section className="card mono muted">
        <div>snapshot_id: {assessment.snapshot_id}</div>
        <div>rubric_version: {assessment.rubric_version}</div>
        <div>harvested_at: {assessment.harvested_at}</div>
        <div>frozen_at: {assessment.frozen_at}</div>
        <div style={{ wordBreak: "break-all" }}>snapshot_hash: {assessment.snapshot_hash}</div>
        <div>
          evidence_records: {assessment.stats?.evidence_records} · pending_review:{" "}
          {assessment.stats?.pending_review} · datasets: {assessment.stats?.datasets} (Tier-1:{" "}
          {assessment.stats?.tier1_datasets})
        </div>
      </section>
    </>
  );
}
