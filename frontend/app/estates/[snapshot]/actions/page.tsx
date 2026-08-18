import { ApiDownNotice, Metric, Pill, gradeColor, severityColor } from "@/components/ui";
import { ApiUnavailable, actionPlan, type ArchitectAction, type Recommendation } from "@/lib/api";

export const dynamic = "force-dynamic";

function Plays({ plays }: { plays: Recommendation[] }) {
  if (plays.length === 0) return null;
  return (
    <div className="plays">
      {plays.map((play) => (
        <details key={play.id}>
          <summary>
            <strong>{play.title}</strong>
            <span className="muted">
              {" "}
              · {play.effort_days.toFixed(0)}d · {play.composite_impact >= 0 ? "+" : ""}
              {play.composite_impact.toFixed(2)} composite
              {play.unblocks.length ? ` · clears ${play.unblocks.join(", ")}` : ""}
            </span>
          </summary>
          <p className="muted" style={{ margin: "0.3rem 0" }}>
            {play.summary}
          </p>
          <ol className="muted" style={{ fontSize: "0.84rem", paddingLeft: "1.2rem", margin: 0 }}>
            {play.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </details>
      ))}
    </div>
  );
}

function FailingSample({ action }: { action: { failing_sample: string[]; failing_total: number } }) {
  if (action.failing_total === 0) return null;
  return (
    <details className="failing">
      <summary className="muted">
        {action.failing_total} failing object{action.failing_total === 1 ? "" : "s"}
      </summary>
      <ul className="mono muted" style={{ fontSize: "0.76rem", margin: "0.3rem 0 0" }}>
        {action.failing_sample.map((target) => (
          <li key={target}>{target}</li>
        ))}
        {action.failing_total > action.failing_sample.length ? (
          <li>… {action.failing_total - action.failing_sample.length} more, in the steward view</li>
        ) : null}
      </ul>
    </details>
  );
}

function ArchitectRow({ action, rank }: { action: ArchitectAction; rank: number }) {
  return (
    <tr>
      <td className="num muted">{rank}</td>
      <td>
        <strong>{action.criterion}</strong>
        <div className="muted" style={{ fontSize: "0.8rem", maxWidth: "56ch" }}>
          {action.check_description}
        </div>
        <FailingSample action={action} />
        <Plays plays={action.plays} />
      </td>
      <td className="muted">{action.pillar}</td>
      <td className="mono" style={{ fontSize: "0.76rem" }}>
        {action.check_id}
      </td>
      <td className="num">
        {action.kind === "no_coverage" ? (
          <Pill label="not measured" color="var(--severity-high)" />
        ) : (
          <span style={{ color: gradeColor(action.score) }}>{action.score?.toFixed(1)}</span>
        )}
      </td>
      <td className="num">{action.target?.toFixed(0) ?? "--"}</td>
      <td className="num">
        {action.kind === "no_coverage" ? (
          <span className="muted mono" style={{ fontSize: "0.74rem" }}>
            needs {action.requires?.join(", ")}
          </span>
        ) : (
          <strong>{action.shortfall?.toFixed(1)}</strong>
        )}
      </td>
    </tr>
  );
}

export default async function EstateActionsPage({
  params,
}: {
  params: Promise<{ snapshot: string }>;
}) {
  const { snapshot } = await params;

  let plan;
  try {
    plan = await actionPlan(snapshot);
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const { summary, projection } = plan;
  const belowTarget = plan.architect_actions.filter((a) => a.kind === "below_target");
  const gaps = plan.architect_actions.filter((a) => a.kind === "no_coverage");
  const decisions = plan.steward_actions.filter((a) => a.kind === "decide");
  const remediations = plan.steward_actions.filter((a) => a.kind === "remediate");

  return (
    <>
      <div className="eyebrow">Action plan</div>
      <p className="lede">
        What to fix, who owns it, and what clearing it is worth. Every row below comes from a check
        that ran against this snapshot — nothing here is advice in general, and each item resolves to
        the objects that actually failed.
      </p>

      <section className="grid cols-4">
        <Metric
          label="Hard blockers"
          value={String(summary.blockers)}
          sub={`${summary.blockers_binding} currently capping the score`}
        />
        <Metric
          label="Architect items"
          value={String(summary.architect_below_target)}
          sub={`plus ${summary.coverage_gaps} coverage gap(s)`}
        />
        <Metric
          label="Steward items"
          value={String(summary.steward_decisions + summary.steward_remediations)}
          sub={`${summary.steward_decisions} decisions · ${summary.steward_remediations} findings`}
        />
        <Metric
          label="Failing objects"
          value={summary.failing_objects.toLocaleString()}
          sub="named individually in the evidence"
        />
      </section>

      <section className="card projection">
        <div>
          <div className="eyebrow">Today</div>
          <strong style={{ color: gradeColor(projection.current_composite) }}>
            {projection.current_composite.toFixed(1)}
          </strong>
          <span className="muted">{projection.current_grade}</span>
        </div>
        <div className="projection-arrow" aria-hidden="true">
          →
        </div>
        <div>
          <div className="eyebrow">If the whole roadmap is delivered</div>
          <strong style={{ color: gradeColor(projection.projected_composite) }}>
            {projection.projected_composite.toFixed(1)}
          </strong>
          <span className="muted">{projection.projected_grade}</span>
        </div>
        <div className="muted" style={{ fontSize: "0.84rem", maxWidth: "44ch" }}>
          {projection.total_effort_days.toFixed(0)} effort days · $
          {projection.total_cost_estimate.toLocaleString()} at the playbook day rate. Impact is
          measured by re-running the scoring engine with each play&apos;s target applied, not
          estimated.
        </div>
      </section>

      {plan.blockers.length ? (
        <>
          <h2>Fix these first — they cap the grade</h2>
          <p className="lede">
            A hard blocker bounds a score regardless of progress everywhere else. Until it clears,
            work on other pillars cannot move the capped number.
          </p>
          {plan.blockers.map((blocker) => (
            <div className="banner" key={`${blocker.override}-${blocker.scope}`}>
              <h3>
                {blocker.scope} capped at {blocker.cap_value}
                {blocker.applied === false ? " (already scoring below the cap)" : ""}
              </h3>
              <p style={{ margin: "0 0 0.4rem" }}>{blocker.rationale}</p>
              <div className="muted mono" style={{ fontSize: "0.78rem" }}>
                {blocker.check_id} · {blocker.check_title} · scores {blocker.current_result?.toFixed(1)} ·{" "}
                {blocker.failing_total} failing object(s) · arithmetic score without the cap{" "}
                {blocker.uncapped_score.toFixed(1)}
              </div>
              <FailingSample action={blocker} />
              <Plays plays={blocker.plays} />
            </div>
          ))}
        </>
      ) : null}

      <h2>For the architect — {belowTarget.length} criteria below target</h2>
      <p className="lede">
        Ranked by what closing the gap is worth: the pillar&apos;s weight in the composite, times the
        criterion&apos;s weight in its pillar, times the distance from the rubric target. That is
        arithmetic over the rubric, not an opinion about difficulty.
      </p>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Criterion and what to do</th>
              <th>Pillar</th>
              <th>Check</th>
              <th className="num">Now</th>
              <th className="num">Target</th>
              <th className="num">Gap</th>
            </tr>
          </thead>
          <tbody>
            {belowTarget.map((action, index) => (
              <ArchitectRow key={action.criterion_key} action={action} rank={index + 1} />
            ))}
          </tbody>
        </table>
      </section>

      {gaps.length ? (
        <>
          <h2>For the architect — {gaps.length} coverage gap(s)</h2>
          <p className="lede">
            These checks never ran: the connectors in this assessment could not observe what they
            require. They are reported, not scored as zero — closing them is a connector or platform
            change rather than a remediation.
          </p>
          <section className="card table-scroll">
            <table>
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Check</th>
                  <th>Pillar</th>
                  <th>Check id</th>
                  <th className="num">Now</th>
                  <th className="num">Target</th>
                  <th className="num">What is missing</th>
                </tr>
              </thead>
              <tbody>
                {gaps.map((action, index) => (
                  <ArchitectRow key={action.criterion_key} action={action} rank={index + 1} />
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}

      <h2>For the steward — {decisions.length} decision(s) waiting</h2>
      {decisions.length ? (
        <section className="card">
          {decisions.map((action) => (
            <div className="steward-item" key={action.evidence_id}>
              <div>
                <span className="mono" style={{ fontSize: "0.78rem" }}>
                  {action.check_id}
                </span>{" "}
                <strong>{action.check_title}</strong>
                <span className="muted">
                  {" "}
                  · result {action.result.toFixed(1)} · confidence {action.confidence.toFixed(2)}
                </span>
              </div>
              <p className="muted" style={{ margin: "0.2rem 0", maxWidth: "82ch" }}>
                {action.rationale}
              </p>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.86rem" }}>{action.action}</p>
              <FailingSample action={action} />
            </div>
          ))}
        </section>
      ) : (
        <section className="card">
          <p className="muted" style={{ margin: 0 }}>
            Nothing is waiting on a human decision in this snapshot.
          </p>
        </section>
      )}

      <h2>For the steward — {remediations.length} finding(s) to work</h2>
      <p className="lede">
        Ordered by severity, then by how many objects fail. Each is a work list with named owners in
        the steward view, not a statistic.
      </p>
      <section className="card">
        {remediations.map((action) => (
          <div className="steward-item" key={action.evidence_id}>
            <div>
              {action.severity ? (
                <Pill label={action.severity} color={severityColor(action.severity)} />
              ) : null}{" "}
              <span className="mono" style={{ fontSize: "0.78rem" }}>
                {action.check_id}
              </span>{" "}
              <strong>{action.check_title}</strong>
              <span className="muted"> · scores {action.result.toFixed(1)}</span>
            </div>
            <p className="muted" style={{ margin: "0.2rem 0", maxWidth: "82ch" }}>
              {action.rationale}
            </p>
            <p style={{ margin: "0.2rem 0 0", fontSize: "0.86rem" }}>{action.action}</p>
            <FailingSample action={action} />
          </div>
        ))}
      </section>

      <h2>Sequenced guidance — what makes this platform AI-ready</h2>
      <p className="lede">
        The same plays, in the order that pays: quick wins first, then structural work, then
        strategic. The projected grade after each horizon comes from re-scoring, so it is a
        measurement of this estate rather than a rule of thumb.
      </p>
      {plan.horizons.map((horizon) => (
        <section className="card" key={horizon.horizon} style={{ marginBottom: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>
            {horizon.label} · {horizon.recommendations.length} play(s) ·{" "}
            {horizon.effort_days.toFixed(0)} days →{" "}
            <span style={{ color: gradeColor(horizon.projected_composite) }}>
              {horizon.projected_composite.toFixed(1)} {horizon.projected_grade}
            </span>
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Play</th>
                  <th>Pillar</th>
                  <th className="num">Effort</th>
                  <th className="num">Impact</th>
                  <th>Clears</th>
                </tr>
              </thead>
              <tbody>
                {horizon.recommendations.map((rec) => (
                  <tr key={rec.id}>
                    <td>
                      <strong>{rec.title}</strong>
                      <div className="muted" style={{ fontSize: "0.8rem", maxWidth: "62ch" }}>
                        {rec.summary}
                      </div>
                      <details style={{ marginTop: "0.3rem" }}>
                        <summary className="muted" style={{ cursor: "pointer", fontSize: "0.8rem" }}>
                          Steps
                        </summary>
                        <ol
                          className="muted"
                          style={{ fontSize: "0.82rem", paddingLeft: "1.2rem", margin: "0.2rem 0 0" }}
                        >
                          {rec.steps.map((step) => (
                            <li key={step}>{step}</li>
                          ))}
                        </ol>
                      </details>
                    </td>
                    <td className="muted">{rec.pillar_key}</td>
                    <td className="num">{rec.effort_days.toFixed(0)}d</td>
                    <td className="num">
                      {rec.composite_impact >= 0 ? "+" : ""}
                      {rec.composite_impact.toFixed(2)}
                    </td>
                    <td className="muted">{rec.unblocks.join(", ") || "--"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  );
}
