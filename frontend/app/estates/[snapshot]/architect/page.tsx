import { ApiDownNotice, EvidenceItem, gradeColor } from "@/components/ui";
import { ApiUnavailable, architectView } from "@/lib/api";

export const dynamic = "force-dynamic";

function Heatmap({
  title,
  rows,
}: {
  title: string;
  rows: { key: string; pillars: Record<string, number> }[];
}) {
  const pillars = Array.from(new Set(rows.flatMap((row) => Object.keys(row.pillars)))).sort();
  if (rows.length === 0) return null;
  return (
    <section className="card table-scroll" style={{ marginBottom: "1rem" }}>
      <h3>{title}</h3>
      <table className="heatmap">
        <thead>
          <tr>
            <th />
            {pillars.map((pillar) => (
              <th key={pillar}>{pillar.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{row.key}</td>
              {pillars.map((pillar) => {
                const value = row.pillars[pillar];
                return (
                  <td
                    key={pillar}
                    className="cell"
                    style={{
                      background:
                        value == null
                          ? "var(--surface-sunken)"
                          : `color-mix(in srgb, ${gradeColor(value)} 65%, white)`,
                    }}
                    title={`${row.key} · ${pillar}: ${value?.toFixed(1) ?? "not measured"}`}
                  >
                    {value == null ? "--" : value.toFixed(0)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default async function EstateArchitectPage({
  params,
}: {
  params: Promise<{ snapshot: string }>;
}) {
  const { snapshot } = await params;

  let view;
  try {
    view = await architectView(snapshot);
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const byPillar = new Map<string, typeof view.criteria>();
  for (const criterion of view.criteria) {
    const key = criterion.parent_key ?? "other";
    byPillar.set(key, [...(byPillar.get(key) ?? []), criterion]);
  }
  const pillarScores = new Map(
    view.scores.filter((s) => s.scope === "pillar").map((s) => [s.key, s]),
  );

  return (
    <>
      <div className="eyebrow">Architect view</div>
      <p className="lede">
        Every criterion below expands to the evidence records that produced it — check, target,
        result, confidence and rationale. Criteria with no evidence are reported as unmeasured, never
        scored as zero.
      </p>

      <Heatmap title="By platform" rows={view.heatmap_by_platform} />
      <Heatmap title="By business domain" rows={view.heatmap_by_domain} />

      <h2>Criteria and evidence</h2>
      {Array.from(byPillar.entries())
        .sort((a, b) => (pillarScores.get(a[0])?.score ?? 0) - (pillarScores.get(b[0])?.score ?? 0))
        .map(([pillarKey, criteria]) => {
          const pillar = pillarScores.get(pillarKey);
          return (
            <section className="card" key={pillarKey} style={{ marginBottom: "1rem" }}>
              <h3 style={{ display: "flex", gap: "0.6rem", alignItems: "baseline" }}>
                <span>{pillar?.name ?? pillarKey}</span>
                <span
                  className="mono"
                  style={{ color: gradeColor(pillar?.score ?? null), fontWeight: 700 }}
                >
                  {pillar?.score.toFixed(1)}
                </span>
                {pillar?.capped_by ? (
                  <span className="muted mono">capped by {pillar.capped_by}</span>
                ) : null}
              </h3>
              {criteria
                .sort((a, b) => a.score - b.score)
                .map((criterion) => (
                  <div key={criterion.key} style={{ marginBottom: "0.4rem" }}>
                    <div style={{ display: "flex", gap: "0.6rem", alignItems: "baseline" }}>
                      <strong style={{ fontSize: "0.9rem" }}>{criterion.name}</strong>
                      <span
                        className="mono"
                        style={{ color: gradeColor(criterion.score), fontWeight: 700 }}
                      >
                        {criterion.score.toFixed(1)}
                      </span>
                      <span className="muted mono" style={{ marginLeft: "auto" }}>
                        weight {criterion.weight}
                      </span>
                    </div>
                    {criterion.evidence.map((record) => (
                      <EvidenceItem key={record.id} record={record} />
                    ))}
                  </div>
                ))}
            </section>
          );
        })}

      {view.unmeasured_criteria.length || view.checks_skipped.length ? (
        <>
          <h2>Coverage gaps</h2>
          <section className="card">
            <h3>Unmeasured criteria ({view.unmeasured_criteria.length})</h3>
            <p className="muted mono">{view.unmeasured_criteria.join(", ") || "none"}</p>
            <h3 style={{ marginTop: "1rem" }}>
              Checks skipped for missing connector capability ({view.checks_skipped.length})
            </h3>
            <p className="muted mono">{view.checks_skipped.join(", ") || "none"}</p>
            <p className="muted" style={{ marginBottom: 0 }}>
              These are reported rather than scored: a check with no evidence source is an absence of
              measurement, not a score of zero. Closing them requires additional connector coverage.
            </p>
          </section>
        </>
      ) : null}
    </>
  );
}
