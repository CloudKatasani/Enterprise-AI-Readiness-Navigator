import { ApiDownNotice, EvidenceItem, Metric, NoSnapshotNotice } from "@/components/ui";
import { ApiUnavailable, latestSnapshotId, stewardView } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function StewardPage() {
  let snapshotId: string | null;
  try {
    snapshotId = await latestSnapshotId();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }
  if (!snapshotId) return <NoSnapshotNotice />;

  const view = await stewardView(snapshotId);

  return (
    <>
      <div className="eyebrow">Steward view</div>
      <h1>Review queue and findings</h1>
      <p className="lede">
        Low-confidence inferences sit here until a human accepts or rejects them — they do not
        influence the score in the meantime. Accepting one re-scores the snapshot and records who
        decided.
      </p>

      <section className="grid cols-3">
        <Metric
          label="Pending review"
          value={String(view.workload.pending_review)}
          sub="inferred findings below the confidence threshold"
        />
        <Metric
          label="Open findings"
          value={String(view.workload.open_findings)}
          sub="accepted checks with failing targets"
        />
        <Metric
          label="Failing targets"
          value={view.workload.failing_targets.toLocaleString()}
          sub="individual objects to remediate"
        />
      </section>

      <h2>Low-confidence review queue</h2>
      <section className="card">
        {view.review_queue.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            Nothing awaiting review in this snapshot.
          </p>
        ) : (
          view.review_queue.map((record) => (
            <div key={record.id}>
              <EvidenceItem record={record} />
              <div className="muted mono" style={{ padding: "0 0 0.6rem" }}>
                Decide with: POST /api/evidence/{record.id}/review {"{"}&quot;decision&quot;:
                &quot;accepted&quot;, &quot;reviewer&quot;: &quot;you@example.com&quot;{"}"}
              </div>
            </div>
          ))
        )}
      </section>

      <h2>Findings queue</h2>
      <p className="lede">
        Ordered by severity, then by distance from target. Each expands to the exact objects that
        fail the check, which is the work list a steward can act on.
      </p>
      <section className="card">
        {view.findings_queue.map((record) => (
          <EvidenceItem key={record.id} record={record} />
        ))}
      </section>

      <h2>Draft recommendations awaiting approval</h2>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Play</th>
              <th>Horizon</th>
              <th>Effort</th>
              <th>Impact</th>
              <th>Confidence</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {view.draft_recommendations.map((rec) => (
              <tr key={rec.id}>
                <td>
                  <strong>{rec.title}</strong>
                  <div className="muted" style={{ fontSize: "0.8rem" }}>
                    {rec.rationale}
                  </div>
                  <details style={{ marginTop: "0.35rem" }}>
                    <summary className="muted" style={{ cursor: "pointer", fontSize: "0.8rem" }}>
                      Steps
                    </summary>
                    <ol className="muted" style={{ fontSize: "0.82rem", paddingLeft: "1.2rem" }}>
                      {rec.steps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  </details>
                </td>
                <td className="muted">{rec.horizon.replace(/_/g, " ")}</td>
                <td className="num">{rec.effort_days.toFixed(0)}d</td>
                <td className="num">
                  {rec.composite_impact >= 0 ? "+" : ""}
                  {rec.composite_impact.toFixed(2)}
                </td>
                <td className="num">{rec.confidence.toFixed(2)}</td>
                <td className="mono muted">{rec.evidence_ids.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
