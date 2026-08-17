import Link from "next/link";
import type { Benchmark, Cap, EvidenceRecord, PortfolioIndustry, PortfolioOrg, ScoreLine } from "@/lib/api";

export function gradeColor(score: number | null | undefined): string {
  if (score == null) return "var(--severity-info)";
  if (score >= 90) return "var(--grade-native)";
  if (score >= 75) return "var(--grade-ready)";
  if (score >= 60) return "var(--grade-capable)";
  if (score >= 40) return "var(--grade-emerging)";
  return "var(--grade-risk)";
}

export function severityColor(severity: string): string {
  return `var(--severity-${severity in { critical: 1, high: 1, medium: 1, low: 1 } ? severity : "info"})`;
}

export function Dial({ value, grade, caption }: { value: number | null; grade: string | null; caption: string }) {
  const shown = value ?? 0;
  return (
    <div
      className="dial"
      style={
        {
          "--dial-value": shown,
          "--dial-color": gradeColor(value),
        } as React.CSSProperties
      }
      role="img"
      aria-label={`${caption}: ${value?.toFixed(1) ?? "not scored"} out of 100, grade ${grade ?? "unscored"}`}
    >
      <div className="dial-value">
        <strong>{value == null ? "--" : value.toFixed(1)}</strong>
        <span>
          {grade ?? "unscored"}
          <br />
          {caption}
        </span>
      </div>
    </div>
  );
}

export function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <div className="eyebrow">{label}</div>
      <strong>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </div>
  );
}

export function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span className="pill" style={{ color }}>
      {label}
    </span>
  );
}

/** A pillar bar. The tick marks the cohort median so the score has a reference. */
export function PillarBar({ score, benchmark }: { score: ScoreLine; benchmark?: Benchmark }) {
  return (
    <div className="bar-row">
      <div>
        <div style={{ fontWeight: 600 }}>{score.name}</div>
        <div className="muted" style={{ fontSize: "0.76rem" }}>
          {score.weight > 0 ? `${(score.weight * 100).toFixed(0)}% of composite` : "overlay index"}
          {score.capped_by ? ` · capped by ${score.capped_by}` : ""}
        </div>
      </div>
      <div className="bar-track" title={`${score.score.toFixed(1)} / 100`}>
        <div
          className="bar-fill"
          style={{ width: `${Math.max(score.score, 1)}%`, background: gradeColor(score.score) }}
        />
        {benchmark ? (
          <div
            className="bar-marker"
            style={{ left: `${benchmark.distribution.p50}%` }}
            title={`Cohort median ${benchmark.distribution.p50}`}
          />
        ) : null}
      </div>
      <div className="bar-value">
        {score.score.toFixed(1)}
        {score.capped_by ? (
          <div className="muted" style={{ fontSize: "0.7rem", fontWeight: 400 }}>
            raw {score.raw_score.toFixed(1)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function CapBanner({ cap }: { cap: Cap }) {
  const binding = cap.applied !== false;
  return (
    <div className="banner" style={binding ? undefined : { opacity: 0.82 }}>
      <h3>
        Hard blocker · {cap.scope}{" "}
        {binding
          ? `capped at ${cap.cap_value}`
          : `already scoring below the ${cap.cap_value} cap`}
      </h3>
      <p style={{ margin: "0 0 0.4rem" }}>{cap.rationale}</p>
      <div className="muted mono">
        {cap.check_id} · {cap.failing_targets} failing target(s) · arithmetic score{" "}
        {cap.uncapped_score.toFixed(1)} · override {cap.override}
        {binding ? "" : " · no cap applied, the finding still blocks the programme"}
      </div>
    </div>
  );
}

/** Evidence, with the rationale and failing targets that produced the number. */
export function EvidenceItem({ record }: { record: EvidenceRecord }) {
  return (
    <details className="evidence">
      <summary>
        <Pill label={record.severity} color={severityColor(record.severity)} />
        <span className="mono">{record.check_id}</span>
        <span>{record.check_title}</span>
        <span className="muted" style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>
          {record.result.toFixed(1)}
        </span>
      </summary>
      <p className="muted" style={{ margin: "0 0 0.5rem", maxWidth: "78ch" }}>
        {record.rationale}
      </p>
      <div className="mono muted">
        pillar {record.pillar_key} · platform {record.platform} · confidence{" "}
        {record.confidence.toFixed(2)} · status {record.status}
        {record.reviewed_by ? ` · reviewed by ${record.reviewed_by}` : ""}
        {record.failing_target_count ? ` · ${record.failing_target_count} failing target(s)` : ""}
      </div>
      {record.failing_targets?.length ? (
        <ul>
          {record.failing_targets.slice(0, 60).map((target) => (
            <li key={target}>{target}</li>
          ))}
          {record.failing_targets.length > 60 ? (
            <li>… {record.failing_targets.length - 60} more</li>
          ) : null}
        </ul>
      ) : null}
    </details>
  );
}

/** Which of an estate's role pages a portfolio link opens. */
export type EstateView = "executive" | "architect" | "steward";

/** Every estate has its own page; the role views are children of that page. */
export function estateHref(snapshotId: string, view: EstateView = "executive"): string {
  return view === "executive" ? `/estates/${snapshotId}` : `/estates/${snapshotId}/${view}`;
}

/** One assessed organisation in the portfolio, linking to its own page. */
export function OrgCard({
  org,
  selected = false,
  view = "executive",
}: {
  org: PortfolioOrg;
  selected?: boolean;
  view?: EstateView;
}) {
  const accent = gradeColor(org.composite_score);
  return (
    <Link
      href={estateHref(org.snapshot_id, view)}
      className="org-card"
      aria-current={selected}
      style={{ "--org-accent": accent } as React.CSSProperties}
    >
      <div className="org-name">
        <span>{org.tenant}</span>
        <span className="org-score">{org.composite_score?.toFixed(1) ?? "--"}</span>
      </div>
      <div className="org-grade">{org.grade ?? "unscored"}</div>
      <div className="org-meta">
        <span>Agent Readiness Index {org.ari_score?.toFixed(0) ?? "--"}</span>
        <span>RAG Readiness Index {org.rri_score?.toFixed(0) ?? "--"}</span>
        <span>{org.size_band.replace(/_/g, " ")}</span>
        {org.hard_blockers > 0 ? (
          <span className="org-blockers">
            {org.hard_blockers} hard blocker{org.hard_blockers === 1 ? "" : "s"}
            {org.hard_blockers_binding === 0 ? " (score already below caps)" : ""}
          </span>
        ) : (
          <span>no hard blockers</span>
        )}
      </div>
    </Link>
  );
}

/** The portfolio: assessed organisations grouped by industry. */
export function Portfolio({
  industries,
  selectedSnapshot,
  view = "executive",
}: {
  industries: PortfolioIndustry[];
  selectedSnapshot?: string;
  view?: EstateView;
}) {
  return (
    <>
      {industries.map((industry) => (
        <div className="industry" key={industry.industry}>
          <div className="industry-head">
            <h3>{industry.industry_label}</h3>
            <span className="muted" style={{ fontSize: "0.8rem" }}>
              {industry.organisations.length} assessed
              {industry.median_composite != null
                ? ` · median composite ${industry.median_composite.toFixed(1)}`
                : ""}
            </span>
          </div>
          <div className="org-grid">
            {industry.organisations.map((org) => (
              <OrgCard
                key={org.snapshot_id}
                org={org}
                view={view}
                selected={org.snapshot_id === selectedSnapshot}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

export function BenchmarkRow({ benchmark }: { benchmark: Benchmark }) {
  return (
    <tr>
      <td>{benchmark.label ?? benchmark.metric_key}</td>
      <td className="num">{benchmark.score.toFixed(1)}</td>
      <td className="num">p{benchmark.percentile.toFixed(0)}</td>
      <td className="num muted">
        {benchmark.distribution.p25}/{benchmark.distribution.p50}/{benchmark.distribution.p75}/
        {benchmark.distribution.p90}
      </td>
      <td className="muted">
        {benchmark.cohort_definition.industry}, {benchmark.cohort_definition.size_band}, n=
        {benchmark.cohort_definition.n}
        {benchmark.reliable ? "" : " (below minimum cohort size)"}
      </td>
    </tr>
  );
}

/** Rendered when the backend is not running — the most likely first-run state. */
export function ApiDownNotice({ detail }: { detail: string }) {
  return (
    <div className="notice">
      <h3>The EAIRN API is not reachable</h3>
      <p className="muted">
        The Portal renders live snapshot state from the backend. Start it, seed a demo estate, and
        reload:
      </p>
      <pre className="mono" style={{ overflowX: "auto" }}>
        {`cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m eairn.seed.bootstrap
.venv/bin/uvicorn eairn.main:app --port 8000`}
      </pre>
      <p className="muted mono" style={{ marginBottom: 0 }}>
        {detail}
      </p>
    </div>
  );
}

/** An estate URL that does not match any snapshot in the portfolio. */
export function UnknownEstateNotice({ snapshotId }: { snapshotId: string }) {
  return (
    <div className="notice">
      <h3>No such assessed estate</h3>
      <p className="muted">
        Snapshot <code>{snapshotId}</code> is not in the portfolio. Snapshots are immutable, so a
        link only breaks when the estate was never assessed on this instance — or the database was
        re-seeded since the link was made.
      </p>
      <p style={{ marginBottom: 0 }}>
        <Link href="/">← Back to all assessed estates</Link>
      </p>
    </div>
  );
}

export function NoSnapshotNotice() {
  return (
    <div className="notice">
      <h3>No assessments yet</h3>
      <p className="muted">
        The API is up but no snapshot has been produced. Seed the deterministic demo estate with{" "}
        <code>python -m eairn.seed.bootstrap</code>, or run an assessment against a configured
        connector via <code>POST /api/assessments</code>.
      </p>
    </div>
  );
}
