import Link from "next/link";
import { ApiDownNotice, NoSnapshotNotice, Pill, estateHref, gradeColor } from "@/components/ui";
import {
  ApiUnavailable,
  methodology,
  portfolio,
  type MethodologyCriterion,
  type MethodologyPillar,
  type MethodologyView,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const pct = (share: number | null | undefined) =>
  share == null ? "0%" : `${(share * 100).toFixed(share * 100 < 10 ? 1 : 0)}%`;

const yesNo = (value: boolean) => (value ? "yes" : "no");

/** Three different absences; the page never lets them read as one. */
const GAP_LABELS = {
  missing_capability: "connector cannot see it",
  held_for_review: "waiting on a reviewer",
  nothing_to_measure: "nothing of this kind in the estate",
} as const;

const GAP_COLORS = {
  missing_capability: "var(--severity-high)",
  held_for_review: "var(--severity-medium)",
  nothing_to_measure: "var(--severity-info)",
} as const;

/** A tick or cross next to the recomputed arithmetic. */
function Reconciled({ ok }: { ok: boolean }) {
  return (
    <Pill
      label={ok ? "recomputed here, matches the engine" : "does not match the engine"}
      color={ok ? "var(--grade-ready)" : "var(--severity-critical)"}
    />
  );
}

/** The measured quantity behind one evidence record, in the check's own units. */
function Measurement({ measured }: { measured: Record<string, unknown> }) {
  const entries = Object.entries(measured).filter(([, value]) => typeof value !== "object");
  if (entries.length === 0) return <span className="muted">—</span>;
  // Ratios arrive as raw floats; binary-float tails are noise, not precision.
  const shown = (value: unknown) =>
    typeof value === "number" && !Number.isInteger(value) ? Number(value.toFixed(4)) : value;
  return (
    <span className="mono" style={{ fontSize: "0.76rem" }}>
      {entries.map(([key, value]) => `${key}=${shown(value)}`).join(" · ")}
    </span>
  );
}

/** Step 1: one check, one evidence record, one number — narrated field by field. */
function WorkedEvidence({ criterion, pillar }: { criterion: MethodologyCriterion; pillar: MethodologyPillar }) {
  const record = criterion.evidence[0];
  if (!record) return null;
  const measured = record.measured as Record<string, unknown>;
  const numerator = measured.numerator;
  const denominator = measured.denominator;
  return (
    <section className="card">
      <h3 style={{ marginTop: 0 }}>
        {record.check_id} · {criterion.check_title}
      </h3>
      <p className="muted" style={{ maxWidth: "80ch" }}>
        {criterion.description || criterion.check_description}
      </p>

      <div className="calc">
        <div className="calc-step">
          <div className="eyebrow">1 · what was counted</div>
          <Measurement measured={measured} />
          <p className="muted" style={{ margin: "0.3rem 0 0", fontSize: "0.84rem" }}>
            Counted from the harvested estate above — no customer row was read to produce it.
          </p>
        </div>
        <div className="calc-step">
          <div className="eyebrow">2 · the result</div>
          <span className="mono">
            {numerator != null && denominator != null
              ? `${numerator} ÷ ${denominator} × 100 = ${record.result.toFixed(1)}`
              : `${record.result.toFixed(1)} out of 100`}
          </span>
          <p className="muted" style={{ margin: "0.3rem 0 0", fontSize: "0.84rem" }}>
            Severity <strong>{record.severity}</strong>
            {record.failing_target_count
              ? ` · ${record.failing_target_count} object(s) fail this check`
              : ""}
          </p>
        </div>
        <div className="calc-step">
          <div className="eyebrow">3 · how much it is trusted</div>
          <span className="mono">confidence {record.confidence.toFixed(2)}</span>
          <p className="muted" style={{ margin: "0.3rem 0 0", fontSize: "0.84rem" }}>
            Status <strong>{record.status}</strong>. Anything below the rubric threshold waits for a
            human decision instead of moving the score.
          </p>
        </div>
        <div className="calc-step">
          <div className="eyebrow">4 · where it lands</div>
          <span className="mono">
            {pillar.name} · weight {criterion.weight} of {pillar.criteria_weight_total}
          </span>
          <p className="muted" style={{ margin: "0.3rem 0 0", fontSize: "0.84rem" }}>
            Contributes {criterion.contribution?.toFixed(1)} to this pillar&apos;s weighted numerator.
          </p>
        </div>
      </div>

      <p style={{ marginBottom: "0.3rem" }}>
        <strong>The rationale recorded with it:</strong>
      </p>
      <p className="muted" style={{ margin: 0, maxWidth: "82ch" }}>
        {record.rationale}
      </p>
      {record.failing_sample?.length ? (
        <>
          <p style={{ margin: "0.8rem 0 0.3rem" }}>
            <strong>The objects that failed</strong> (first {record.failing_sample.length} of{" "}
            {record.failing_target_count}) — this is the work list, not a statistic:
          </p>
          <ul className="mono muted" style={{ margin: 0, fontSize: "0.78rem" }}>
            {record.failing_sample.map((target) => (
              <li key={target}>{target}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function PillarWorking({ pillar, open }: { pillar: MethodologyPillar; open: boolean }) {
  const accent = gradeColor(pillar.score);
  return (
    <details className="card working" open={open} style={{ borderLeft: `4px solid ${accent}` }}>
      <summary>
        <span style={{ fontWeight: 650 }}>{pillar.name}</span>
        <span className="mono" style={{ color: accent, fontWeight: 700 }}>
          {pillar.score?.toFixed(1) ?? "--"}
        </span>
        <span className="muted" style={{ fontSize: "0.8rem" }}>
          {pillar.weight > 0 ? `${(pillar.weight * 100).toFixed(0)}% of composite` : "overlay only"}
          {pillar.capped_by ? ` · capped by ${pillar.capped_by}` : ""}
        </span>
        <span className="muted" style={{ marginLeft: "auto", fontSize: "0.8rem" }}>
          {pillar.criteria.filter((c) => c.measured).length}/{pillar.criteria.length} criteria measured
        </span>
      </summary>

      <p className="muted" style={{ maxWidth: "80ch" }}>
        <strong>Core question:</strong> {pillar.core_question}
      </p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Criterion</th>
              <th>Check</th>
              <th>What was measured</th>
              <th className="num">Score</th>
              <th className="num">Weight</th>
              <th className="num">score × weight</th>
            </tr>
          </thead>
          <tbody>
            {pillar.criteria.map((criterion) => (
              <tr key={criterion.key} style={criterion.measured ? undefined : { opacity: 0.65 }}>
                <td>
                  <strong>{criterion.name}</strong>
                  {criterion.target != null ? (
                    <div className="muted" style={{ fontSize: "0.76rem" }}>
                      target {criterion.target}
                    </div>
                  ) : null}
                </td>
                <td className="mono" style={{ fontSize: "0.78rem" }}>
                  {criterion.check_id}
                </td>
                <td>
                  {criterion.measured && criterion.evidence[0] ? (
                    <Measurement measured={criterion.evidence[0].measured as Record<string, unknown>} />
                  ) : (
                    <span className="muted">no accepted evidence — excluded, not scored as zero</span>
                  )}
                </td>
                <td className="num" style={{ color: gradeColor(criterion.score) }}>
                  {criterion.score?.toFixed(1) ?? "--"}
                </td>
                <td className="num">{criterion.weight}</td>
                <td className="num">{criterion.contribution?.toFixed(1) ?? "--"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={5}>
                <strong>Weighted mean of the measured criteria</strong>
                <div className="muted" style={{ fontSize: "0.78rem" }}>
                  {pillar.weighted_numerator?.toFixed(1)} ÷ {pillar.weight_denominator} ={" "}
                  {pillar.recomputed_raw?.toFixed(2)}
                </div>
              </td>
              <td className="num">
                <strong>{pillar.recomputed_raw?.toFixed(2) ?? "--"}</strong>
              </td>
            </tr>
            {pillar.capped_by ? (
              <tr>
                <td colSpan={5}>
                  <strong>Hard blocker {pillar.capped_by}</strong>
                  <div className="muted" style={{ fontSize: "0.78rem" }}>
                    {pillar.cap?.rationale}
                  </div>
                </td>
                <td className="num" style={{ color: "var(--severity-critical)" }}>
                  <strong>{pillar.score?.toFixed(2)}</strong>
                </td>
              </tr>
            ) : null}
          </tfoot>
        </table>
      </div>

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
        <Reconciled ok={pillar.reconciles} />
        <span className="muted mono" style={{ fontSize: "0.76rem" }}>
          engine raw {pillar.engine_raw?.toFixed(4)} · final {pillar.score?.toFixed(2)} ·{" "}
          {pillar.grade ?? "unscored"}
        </span>
        {pillar.unmeasured_criteria.length ? (
          <span className="muted" style={{ fontSize: "0.78rem" }}>
            {pct(pillar.unmeasured_weight_share)} of this pillar&apos;s criterion weight had no
            evidence ({pillar.unmeasured_criteria.join(", ")}).
          </span>
        ) : null}
      </div>
    </details>
  );
}

export default async function MethodologyPage({
  searchParams,
}: {
  searchParams: Promise<{ estate?: string }>;
}) {
  const requested = (await searchParams).estate;

  let view: MethodologyView;
  let industries;
  try {
    [view, industries] = await Promise.all([methodology(requested), portfolio()]);
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }
  if (!view.assessment) return <NoSnapshotNotice />;

  const organisations = industries.flatMap((industry) => industry.organisations);
  const connector = view.provenance.connectors[0];
  const config = connector?.config ?? {};
  const sample = view.provenance.sample;
  const totals = view.evidence_totals;

  // The most instructive worked example is the weakest criterion that counted a
  // ratio: it shows the division, the failing objects, and a score worth acting
  // on. Criteria measured some other way are the fallback, never the first pick.
  const measuredCriteria = view.pillars.flatMap((pillar) =>
    pillar.criteria
      .filter((c) => c.measured && c.evidence.length > 0)
      .map((c) => ({ pillar, criterion: c })),
  );
  const isRatio = ({ criterion }: { criterion: MethodologyCriterion }) =>
    (criterion.evidence[0].measured as Record<string, unknown>).denominator != null ? 0 : 1;
  const worked = measuredCriteria.sort(
    (a, b) => isRatio(a) - isRatio(b) || (a.criterion.score ?? 0) - (b.criterion.score ?? 0),
  )[0];

  return (
    <>
      <div className="eyebrow">Methodology</div>
      <h1>How a pillar score is calculated</h1>
      <p className="lede">
        Every number in this product is a weighted mean of machine-measured checks, and every check is
        a count of objects in the harvested metadata. This page works the whole calculation through
        one estate — from a single evidence record to the composite grade — and then states plainly
        what was <em>not</em> measured. All arithmetic below is recomputed on this page from the
        stored score lines and compared with what the Scoring Engine wrote.
      </p>

      <nav className="jumplinks">
        <a href="#data">1 · The sample data</a>
        <a href="#evidence">2 · One check → one evidence record</a>
        <a href="#pillars">3 · Criteria → pillar score</a>
        <a href="#composite">4 · Pillars → composite grade</a>
        <a href="#blockers">5 · Hard blockers</a>
        <a href="#indices">6 · Overlay indices</a>
        <a href="#confidence">7 · Confidence</a>
        <a href="#missing">8 · What is missing</a>
      </nav>

      <h2 id="data">1 · The sample data these scores are calculated from</h2>
      <p className="lede">
        The worked example is <strong>{view.assessment.tenant}</strong>
        {view.requested_snapshot ? (
          <>, one of the {organisations.length} estates in this portfolio.</>
        ) : (
          <>
            {" "}
            — the median estate of the {organisations.length} in this portfolio, chosen as the default
            because it shows both a pillar that scores well and a pillar that does not.
          </>
        )}{" "}
        Pick any other estate to re-work the same calculation against its evidence.
      </p>

      <div className="estate-picker">
        {organisations.map((org) => (
          <Link
            key={org.snapshot_id}
            href={`/methodology?estate=${org.snapshot_id}`}
            aria-current={org.snapshot_id === view.assessment.snapshot_id}
          >
            {org.tenant}
            <span className="mono">{org.composite_score?.toFixed(1) ?? "--"}</span>
          </Link>
        ))}
      </div>

      {config.synthetic ? (
        <div className="banner banner-info">
          <h3>This estate is synthetic — and deterministically reproducible</h3>
          <p style={{ margin: "0 0 0.4rem" }}>
            No customer system was contacted. The demo connector generated a mimic estate from two
            profiles: <strong>{config.industry_label}</strong> decides which business domains exist,
            which platform they sit on and where regulated data concentrates; maturity{" "}
            <strong>{String(config.maturity).replace(/_/g, "-")}</strong> decides how far the
            governance programme has actually got — {config.maturity_label?.toLowerCase()}. Neither
            profile sets a score: they set estate facts, and the checks measure whatever those facts
            support. A real assessment replaces this connector with a read-only harvest of the
            customer&apos;s own catalog; nothing else in the calculation changes.
          </p>
          <div className="muted mono" style={{ fontSize: "0.78rem" }}>
            connector {connector?.connector} · platform {config.platform} · seed {config.seed} ·
            harvest anchor {config.harvest_anchor}
          </div>
        </div>
      ) : null}

      <section className="card">
        <h3 style={{ marginTop: 0 }}>What was harvested</h3>
        <div className="count-grid">
          {Object.entries(connector?.counts ?? {}).map(([key, value]) => (
            <div className="count" key={key}>
              <strong>{value.toLocaleString()}</strong>
              <span>{key.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
        <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
          Those objects produced <strong>{totals.records}</strong> evidence records across{" "}
          {totals.checks_with_evidence} of {totals.registered_checks} registered checks (
          {totals.context_records} further records are per-domain slices carried for drill-through and
          are deliberately not scored). {totals.accepted} were accepted, {totals.pending_review} are
          held for human review, and {totals.failing_targets.toLocaleString()} individual objects fail
          at least one check.
        </p>
      </section>

      {config.domains?.length ? (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Business domains in this estate</h3>
          <div className="chips">
            {config.domains.map((domain: { schema: string; domain: string; base_tier: number }) => (
              <span
                className="chip"
                key={domain.schema}
                title={`schema ${domain.schema}, base tier ${domain.base_tier}`}
              >
                {domain.domain}
                <span className="muted"> · tier {domain.base_tier}</span>
                {config.sensitive_domains?.includes(domain.domain) ? (
                  <span style={{ color: "var(--severity-high)" }}> · regulated</span>
                ) : null}
              </span>
            ))}
          </div>
          <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
            Tier drives expectation, not score: a Tier-1 domain is held to the full metadata,
            ownership and protection bar, while a sandbox schema is not. Regulated domains are where
            the Security pillar&apos;s classified-column checks concentrate.
          </p>
        </section>
      ) : null}

      {sample ? (
        <>
          <h3>A slice of the actual objects a check sees</h3>
          <section className="card table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Domain</th>
                  <th className="num">Tier</th>
                  <th>Owner</th>
                  <th>Described</th>
                  <th>Certified</th>
                  <th className="num">Columns</th>
                </tr>
              </thead>
              <tbody>
                {sample.datasets.map((dataset) => (
                  <tr key={dataset.urn}>
                    <td className="mono" style={{ fontSize: "0.78rem" }}>
                      {dataset.urn}
                    </td>
                    <td>{dataset.domain ?? "--"}</td>
                    <td className="num">{dataset.tier}</td>
                    <td className="muted" style={{ fontSize: "0.8rem" }}>
                      {dataset.owner ?? "none"}
                      {dataset.owner ? (dataset.owner_verified ? " (verified)" : " (unverified)") : ""}
                    </td>
                    <td>{yesNo(dataset.described)}</td>
                    <td>{yesNo(dataset.certified)}</td>
                    <td className="num">{dataset.column_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {sample.datasets[0] ? (
            <section className="card table-scroll">
              <h3 style={{ marginTop: 0 }}>
                Columns of <span className="mono">{sample.datasets[0].name}</span>
              </h3>
              <table>
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Type</th>
                    <th>Classification</th>
                    <th>Described</th>
                    <th>Protection</th>
                  </tr>
                </thead>
                <tbody>
                  {sample.datasets[0].columns.map((column) => (
                    <tr key={column.name}>
                      <td className="mono">{column.name}</td>
                      <td className="muted">{column.data_type}</td>
                      <td>{column.classification ?? <span className="muted">unclassified</span>}</td>
                      <td>{yesNo(column.described)}</td>
                      <td>
                        {column.protected ? (
                          column.protection_kind
                        ) : (
                          <span className="muted">none</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
                Column names, types, classifications and protections are metadata. The values in these
                columns are never read — that boundary is what keeps a readiness score free of
                customer data.
              </p>
            </section>
          ) : null}

          <div className="grid cols-2">
            <section className="card">
              <h3 style={{ marginTop: 0 }}>Protection policies</h3>
              {sample.policies.length ? (
                sample.policies.map((policy) => (
                  <div key={policy.name} style={{ marginBottom: "0.5rem" }}>
                    <span className="mono">{policy.name}</span>{" "}
                    <span className="muted">
                      · {policy.policy_type} · bound to tag {policy.bound_to_tag ?? "none"} ·{" "}
                      {policy.target_count} target(s)
                    </span>
                  </div>
                ))
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  None harvested — which is itself the finding the Security pillar reports.
                </p>
              )}
            </section>
            <section className="card">
              <h3 style={{ marginTop: 0 }}>Agents and corpora</h3>
              {sample.agents.map((agent) => (
                <div key={agent.name} className="muted" style={{ fontSize: "0.84rem" }}>
                  <span className="mono">{agent.name}</span> · identity {agent.identity_kind} · scoped
                  roles {yesNo(agent.scoped_roles)} · audit {yesNo(agent.action_audit)} · approval gate{" "}
                  {yesNo(agent.write_approval_gate)}
                </div>
              ))}
              {sample.rag_corpora.map((corpus) => (
                <div key={corpus.name} className="muted" style={{ fontSize: "0.84rem" }}>
                  <span className="mono">{corpus.name}</span> · {corpus.indexed_doc_count} of{" "}
                  {corpus.authoritative_doc_count} docs indexed · ACLs propagated{" "}
                  {yesNo(corpus.acl_propagated)} · citations enforced {yesNo(corpus.citation_enforced)}
                </div>
              ))}
            </section>
          </div>
        </>
      ) : (
        <p className="muted">
          The canonical tables hold this tenant&apos;s most recent harvest, and this snapshot is not
          it — so the sample objects are not shown rather than shown misleadingly. The counts above
          come from the harvest run recorded with this snapshot.
        </p>
      )}

      <h2 id="evidence">2 · One check becomes one evidence record</h2>
      <p className="lede">
        A check is a pure function of harvested metadata. It counts objects that meet a condition,
        divides by the objects in scope, and records the result with its confidence, its rationale and
        the exact objects that failed. Here is the weakest coverage ratio measured in this estate, in full.
      </p>
      {worked ? <WorkedEvidence criterion={worked.criterion} pillar={worked.pillar} /> : null}

      <h2 id="pillars">3 · Criteria become a pillar score</h2>
      <p className="lede">
        A pillar is the weighted mean of its criteria — weights come from{" "}
        <span className="mono">rubric_v{view.rubric.version}</span>, not from code. Criteria with no
        accepted evidence are excluded from both sides of the division, so an unmeasured criterion
        lowers the evidence base rather than the score, and is reported in section 8. Expand any pillar to see
        its full arithmetic.
      </p>
      {view.pillars.map((pillar, index) => (
        <PillarWorking key={pillar.key} pillar={pillar} open={index === 0} />
      ))}

      <h2 id="composite">4 · Pillars become the composite grade</h2>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Pillar</th>
              <th className="num">Score</th>
              <th className="num">Weight</th>
              <th className="num">score × weight</th>
            </tr>
          </thead>
          <tbody>
            {view.composite.terms.map((term) => (
              <tr key={term.key}>
                <td>
                  {term.name}
                  {term.capped_by ? (
                    <span className="muted" style={{ fontSize: "0.76rem" }}> · capped</span>
                  ) : null}
                </td>
                <td className="num" style={{ color: gradeColor(term.score) }}>
                  {term.score.toFixed(2)}
                </td>
                <td className="num">{term.weight}</td>
                <td className="num">{term.contribution.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>
                <strong>Composite</strong>
                <div className="muted" style={{ fontSize: "0.78rem" }}>
                  {view.composite.weighted_numerator?.toFixed(2)} ÷{" "}
                  {view.composite.weight_denominator} = {view.composite.recomputed_raw?.toFixed(2)}
                </div>
              </td>
              <td className="num">
                <strong style={{ color: gradeColor(view.composite.score) }}>
                  {view.composite.score?.toFixed(2)}
                </strong>
              </td>
            </tr>
          </tfoot>
        </table>
        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
          <Reconciled ok={view.composite.reconciles} />
          <span className="muted mono" style={{ fontSize: "0.76rem" }}>
            engine raw {view.composite.engine_raw?.toFixed(4)}
          </span>
        </div>
      </section>

      <section className="card table-scroll">
        <h3 style={{ marginTop: 0 }}>The grade band it lands in</h3>
        <table>
          <thead>
            <tr>
              <th>Grade</th>
              <th className="num">Range</th>
              <th>What it means</th>
            </tr>
          </thead>
          <tbody>
            {view.composite.bands.map((band) => {
              const here = band.grade === view.composite.grade;
              return (
                <tr key={band.grade} style={here ? { background: "var(--surface-sunken)" } : undefined}>
                  <td>
                    <strong style={{ color: here ? gradeColor(view.composite.score) : undefined }}>
                      {band.grade}
                    </strong>
                    {here ? <span className="muted"> ← this estate</span> : null}
                  </td>
                  <td className="num">
                    {band.min}–{band.max}
                  </td>
                  <td className="muted">{band.interpretation}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <h2 id="blockers">5 · Hard blockers cap the arithmetic</h2>
      <p className="lede">
        Some findings bound a score no matter how well everything else does. The caps are rubric data,
        each tied to a specific check and threshold. A blocker is reported whenever its condition
        fires — including when the estate already scores below the cap, where there is nothing left to
        lower.
      </p>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Override</th>
              <th>Fires when</th>
              <th>Caps</th>
              <th>On this estate</th>
            </tr>
          </thead>
          <tbody>
            {view.overrides.map((override) => (
              <tr key={override.key} style={override.fired ? undefined : { opacity: 0.6 }}>
                <td>
                  <span className="mono" style={{ fontSize: "0.78rem" }}>
                    {override.key}
                  </span>
                  <div className="muted" style={{ fontSize: "0.78rem", maxWidth: "52ch" }}>
                    {override.rationale}
                  </div>
                </td>
                <td className="mono" style={{ fontSize: "0.76rem" }}>
                  {override.check_id} {override.condition.replace(/_/g, " ")} {override.threshold}
                </td>
                <td className="mono" style={{ fontSize: "0.78rem" }}>
                  {override.cap_scope} ≤ {override.cap_value}
                </td>
                <td>
                  {override.fired ? (
                    <Pill
                      label={override.applied ? "fired · cap applied" : "fired · already below cap"}
                      color="var(--severity-critical)"
                    />
                  ) : (
                    <span className="muted">not triggered</span>
                  )}
                  {override.failing_targets ? (
                    <div className="muted mono" style={{ fontSize: "0.74rem" }}>
                      {override.failing_targets} failing target(s)
                    </div>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <h2 id="indices">6 · The two overlay indices</h2>
      <p className="lede">
        The Agent Readiness Index and the RAG Readiness Index re-cut the same evidence into dimensions
        that matter to one programme, so an agent or RAG initiative can be funded on its own evidence
        rather than on a general readiness average. They sit outside the composite weighting and carry
        their own grade bands and their own caps.
      </p>
      {view.indices.map((index) => (
        <section className="card table-scroll" key={index.key}>
          <h3 style={{ marginTop: 0 }}>
            {index.name}{" "}
            <span className="mono" style={{ color: gradeColor(index.score) }}>
              {index.score?.toFixed(1)} · {index.grade}
            </span>
          </h3>
          <table>
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Checks it reads</th>
                <th className="num">Score</th>
                <th className="num">Weight</th>
                <th className="num">score × weight</th>
              </tr>
            </thead>
            <tbody>
              {index.dimensions.map((dimension) => (
                <tr key={dimension.key}>
                  <td>
                    <strong>{dimension.name}</strong>
                    <div className="muted" style={{ fontSize: "0.78rem", maxWidth: "48ch" }}>
                      {dimension.description}
                    </div>
                  </td>
                  <td className="mono muted" style={{ fontSize: "0.74rem" }}>
                    {dimension.check_ids.join(", ")}
                  </td>
                  <td className="num" style={{ color: gradeColor(dimension.score) }}>
                    {dimension.score?.toFixed(1) ?? "--"}
                  </td>
                  <td className="num">{dimension.weight}</td>
                  <td className="num">{dimension.contribution?.toFixed(1) ?? "--"}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={4}>
                  <strong>{index.name}</strong>
                  <div className="muted" style={{ fontSize: "0.78rem" }}>
                    {index.weighted_numerator?.toFixed(1)} ÷ {index.weight_denominator} ={" "}
                    {index.recomputed_raw?.toFixed(2)}
                    {index.capped_by ? ` · then capped by ${index.capped_by}` : ""}
                  </div>
                </td>
                <td className="num">
                  <strong style={{ color: gradeColor(index.score) }}>{index.score?.toFixed(2)}</strong>
                </td>
              </tr>
            </tfoot>
          </table>
          <Reconciled ok={index.reconciles} />
        </section>
      ))}

      <h2 id="confidence">7 · Confidence decides what is allowed to count</h2>
      <p className="lede">
        Every record carries a confidence tier. The rubric threshold for this version is{" "}
        <strong>{view.confidence.threshold.toFixed(2)}</strong>: anything at or above it scores,
        anything below it is queued for a human and excluded from the arithmetic until someone
        decides. That is why an inference can never quietly move a grade.
      </p>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Tier</th>
              <th className="num">Confidence</th>
              <th>What it means</th>
              <th>Example</th>
              <th>Counts?</th>
            </tr>
          </thead>
          <tbody>
            {view.confidence.tiers.map((tier) => (
              <tr key={tier.key}>
                <td>
                  <strong>{tier.label}</strong>
                </td>
                <td className="num">{tier.value.toFixed(2)}</td>
                <td className="muted">{tier.meaning}</td>
                <td className="muted" style={{ fontSize: "0.82rem" }}>
                  {tier.example}
                </td>
                <td>
                  <Pill
                    label={tier.scored ? "scores" : "queued for review"}
                    color={tier.scored ? "var(--grade-ready)" : "var(--severity-medium)"}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <h2 id="missing">8 · What is missing from this score</h2>
      <p className="lede">
        A coverage gap that nobody can see reads as a pass. These are the parts of the rubric this
        estate&apos;s evidence did not reach: {pct(view.coverage.composite_weight_unmeasured)} of the
        composite&apos;s criterion weight sits on criteria that produced no score — for one of three
        different reasons, which the table below keeps apart.
      </p>

      <div className="grid cols-3">
        <div className="metric">
          <div className="eyebrow">Criteria unscored</div>
          <strong>{view.coverage.unmeasured_criteria.length}</strong>
          <small>excluded from the mean, never scored as zero</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Checks skipped</div>
          <strong>{view.coverage.checks_skipped.length}</strong>
          <small>connector cannot observe what they require</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Held for review</div>
          <strong>{view.coverage.pending_review.length}</strong>
          <small>below the confidence threshold</small>
        </div>
      </div>

      {view.coverage.unmeasured_criteria.length ? (
        <section className="card table-scroll">
          <h3 style={{ marginTop: 0 }}>Criteria that did not reach the score</h3>
          <table>
            <thead>
              <tr>
                <th>Criterion</th>
                <th>Pillar</th>
                <th>Check</th>
                <th>Kind of gap</th>
                <th>Why it is missing</th>
              </tr>
            </thead>
            <tbody>
              {view.coverage.unmeasured_criteria.map((criterion) => (
                <tr key={criterion.key}>
                  <td>
                    <strong>{criterion.name}</strong>
                  </td>
                  <td className="muted">{criterion.pillar}</td>
                  <td className="mono" style={{ fontSize: "0.78rem" }}>
                    {criterion.check_id}
                  </td>
                  <td>
                    <Pill
                      label={GAP_LABELS[criterion.status ?? "nothing_to_measure"]}
                      color={GAP_COLORS[criterion.status ?? "nothing_to_measure"]}
                    />
                  </td>
                  <td className="muted">{criterion.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
            By pillar:{" "}
            {view.coverage.by_pillar
              .map((p) => `${p.name} ${pct(p.unmeasured_weight_share)} of criterion weight`)
              .join(" · ")}
            .
          </p>
        </section>
      ) : null}

      {view.coverage.checks_skipped.length ? (
        <section className="card table-scroll">
          <h3 style={{ marginTop: 0 }}>Checks skipped for missing connector capability</h3>
          <table>
            <thead>
              <tr>
                <th>Check</th>
                <th>Pillar</th>
                <th>Requires</th>
                <th>Missing</th>
              </tr>
            </thead>
            <tbody>
              {view.coverage.checks_skipped.map((check) => (
                <tr key={check.check_id}>
                  <td>
                    <span className="mono" style={{ fontSize: "0.78rem" }}>
                      {check.check_id}
                    </span>{" "}
                    {check.title}
                  </td>
                  <td className="muted">{check.pillar_key}</td>
                  <td className="mono muted" style={{ fontSize: "0.74rem" }}>
                    {check.requires.join(", ")}
                  </td>
                  <td className="mono" style={{ fontSize: "0.74rem", color: "var(--severity-high)" }}>
                    {check.missing_capabilities.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>No check was skipped for missing capability</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            The connectors in this run could observe everything the check library asks for:{" "}
            <span className="mono" style={{ fontSize: "0.78rem" }}>
              {view.coverage.capabilities_present.join(", ")}
            </span>
            . On a real estate this list is usually shorter, and every check it cannot feed is
            reported here instead of being scored as zero.
          </p>
        </section>
      )}

      {view.coverage.pending_review.length ? (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Evidence held below the confidence threshold</h3>
          {view.coverage.pending_review.map((record) => (
            <div key={record.id} style={{ marginBottom: "0.6rem" }}>
              <span className="mono" style={{ fontSize: "0.78rem" }}>
                {record.check_id}
              </span>{" "}
              {record.check_title}{" "}
              <span className="muted">
                · result {record.result.toFixed(1)} · confidence {record.confidence.toFixed(2)}
              </span>
              <div className="muted" style={{ fontSize: "0.84rem", maxWidth: "80ch" }}>
                {record.rationale}
              </div>
            </div>
          ))}
          <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
            These sit in the steward&apos;s review queue. Accepting one re-scores the snapshot and
            records who decided.
          </p>
        </section>
      ) : null}

      <section className="card">
        <h3 style={{ marginTop: 0 }}>What EAIRN never collects at all</h3>
        <p className="muted">
          These are product boundaries rather than gaps to close, and they are the reason a readiness
          score can be produced without a data-privacy review of the score itself.
        </p>
        <ul style={{ paddingLeft: "1.1rem", marginBottom: 0 }}>
          {view.coverage.never_collected.map((item) => (
            <li key={item.item} style={{ marginBottom: "0.4rem" }}>
              <strong>{item.item}</strong>
              <div className="muted" style={{ fontSize: "0.86rem", maxWidth: "80ch" }}>
                {item.why}
              </div>
            </li>
          ))}
        </ul>
        <p className="muted" style={{ margin: "0.7rem 0 0", fontSize: "0.84rem" }}>
          Row sampling is{" "}
          {view.settings.row_sampling_enabled ? "enabled on this instance" : "disabled on this instance"}
          . It is a separate, permission-gated module: every authorisation is recorded per dataset,
          and no check reads a row without one.
        </p>
      </section>

      <h2>Read the same estate in the role views</h2>
      <p className="lede">
        This page explains the method. The estate&apos;s own pages apply it:{" "}
        <Link href={estateHref(view.assessment.snapshot_id)}>the executive view</Link> for the score
        and roadmap,{" "}
        <Link href={estateHref(view.assessment.snapshot_id, "architect")}>the architect view</Link> for
        every criterion drilled through to its evidence, and{" "}
        <Link href={estateHref(view.assessment.snapshot_id, "steward")}>the steward view</Link> for the
        review queue and the exact failing objects.
      </p>

      <section className="card mono muted">
        <div>rubric: v{view.rubric.version} — {view.rubric.name}</div>
        <div>confidence_threshold: {view.rubric.confidence_threshold}</div>
        <div style={{ wordBreak: "break-all" }}>rubric_source_digest: {view.rubric.source_digest}</div>
        <div>snapshot_id: {view.assessment.snapshot_id}</div>
        <div style={{ wordBreak: "break-all" }}>snapshot_hash: {view.assessment.snapshot_hash}</div>
        <div>
          Replay this snapshot with GET /api/assessments/{view.assessment.snapshot_id}/verify — it
          re-runs the engine over the stored evidence and proves the hash still matches.
        </div>
      </section>
    </>
  );
}
