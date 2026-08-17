import Link from "next/link";
import { ApiDownNotice, Pill, gradeColor } from "@/components/ui";
import {
  ApiUnavailable,
  pillarGuide,
  type PillarGuideEntry,
  type PillarGuideIndex,
  type PillarReference,
  type PillarSpread,
} from "@/lib/api";

export const dynamic = "force-dynamic";

/** Paragraphs from a YAML block scalar. */
function Prose({ text, className }: { text: string; className?: string }) {
  if (!text) return null;
  return (
    <>
      {text
        .trim()
        .split(/\n\s*\n/)
        .map((paragraph, index) => (
          <p key={index} className={className} style={{ maxWidth: "84ch" }}>
            {paragraph.replace(/\s*\n\s*/g, " ")}
          </p>
        ))}
    </>
  );
}

/** How the assessed organizations on this instance actually spread on a pillar. */
function Spread({ spread, capValue }: { spread: PillarSpread | null; capValue?: number }) {
  if (!spread) return null;
  const atCap = capValue != null && Math.abs(spread.median - capValue) < 0.05;
  return (
    <div className="spread">
      <div className="spread-track">
        <div
          className="spread-range"
          style={{
            left: `${spread.min}%`,
            width: `${Math.max(spread.max - spread.min, 1)}%`,
            background: `linear-gradient(90deg, ${gradeColor(spread.min)}, ${gradeColor(spread.max)})`,
          }}
        />
        <div
          className="spread-median"
          style={{ left: `${spread.median}%` }}
          title={`median ${spread.median}`}
        />
      </div>
      <div className="muted" style={{ fontSize: "0.78rem" }}>
        Across the {spread.n} assessed organizations on this instance: lowest{" "}
        <strong style={{ color: gradeColor(spread.min) }}>{spread.min}</strong>, median{" "}
        <strong style={{ color: gradeColor(spread.median) }}>{spread.median}</strong>, highest{" "}
        <strong style={{ color: gradeColor(spread.max) }}>{spread.max}</strong>.
        {atCap
          ? ` The median sits exactly on the ${capValue} cap — the hard blocker below is binding on
             most of this portfolio, not a rare edge case.`
          : ""}
      </div>
    </div>
  );
}

function References({ references }: { references: PillarReference[] }) {
  if (references.length === 0) return null;
  return (
    <div className="refs">
      <h4>References</h4>
      <ol>
        {references.map((reference) => (
          <li key={reference.title}>
            {reference.url ? (
              <a href={reference.url} target="_blank" rel="noreferrer noopener">
                {reference.title}
              </a>
            ) : (
              <span style={{ fontWeight: 600 }}>{reference.title}</span>
            )}
            <div className="muted" style={{ fontSize: "0.8rem" }}>
              {reference.source}
              {reference.note ? ` — ${reference.note}` : ""}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PillarSection({ pillar }: { pillar: PillarGuideEntry }) {
  const accent = gradeColor(pillar.distribution?.median ?? null);
  const overlay = pillar.scoring_mode !== "composite" || pillar.weight === 0;
  return (
    <section className="card pillar-card" id={pillar.key} style={{ borderTop: `4px solid ${accent}` }}>
      <div className="pillar-head">
        <div>
          <h3 style={{ margin: 0 }}>{pillar.name}</h3>
          <div className="muted mono" style={{ fontSize: "0.78rem" }}>
            {pillar.key} · {pillar.criteria.length} criteria
          </div>
        </div>
        <Pill
          label={overlay ? "overlay index — outside the composite" : `${(pillar.weight * 100).toFixed(0)}% of composite`}
          color={overlay ? "var(--ocean-600)" : accent}
        />
      </div>

      <p className="pillar-headline">{pillar.headline}</p>
      <p className="muted" style={{ maxWidth: "84ch" }}>
        <strong>The question it answers:</strong> {pillar.core_question}
      </p>

      <Spread spread={pillar.distribution} capValue={pillar.overrides[0]?.cap_value} />

      <h4>Why it matters</h4>
      <Prose text={pillar.why_it_matters} className="muted" />

      {pillar.ai_impact ? (
        <>
          <h4>What changes when AI consumes it</h4>
          <Prose text={pillar.ai_impact} className="muted" />
        </>
      ) : null}

      <div className="grid cols-2" style={{ marginTop: "0.4rem" }}>
        <div>
          <h4>What goes wrong without it</h4>
          <ul className="muted consequence">
            {pillar.without_it.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>What good looks like</h4>
          <ul className="muted good">
            {pillar.good_looks_like.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="omission">
        <h4 style={{ marginTop: 0 }}>If you leave this pillar out of the assessment</h4>
        <Prose text={pillar.if_unassessed} />
      </div>

      {pillar.overrides.map((override) => (
        <div className="banner" key={override.key} style={{ marginTop: "0.9rem" }}>
          <h3>
            Hard blocker · caps {pillar.name} at {override.cap_value}
          </h3>
          <p style={{ margin: "0 0 0.4rem" }}>{override.rationale}</p>
          <div className="muted mono" style={{ fontSize: "0.76rem" }}>
            fires when {override.check_id} {override.condition.replace(/_/g, " ")} {override.threshold}{" "}
            · override {override.key}
          </div>
        </div>
      ))}

      <h4>What is actually measured</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Criterion</th>
              <th>Check</th>
              <th>What the check counts</th>
              <th className="num">Weight</th>
              <th className="num">Target</th>
            </tr>
          </thead>
          <tbody>
            {pillar.criteria.map((criterion) => (
              <tr key={criterion.key}>
                <td>
                  <strong>{criterion.name}</strong>
                </td>
                <td className="mono" style={{ fontSize: "0.78rem" }}>
                  {criterion.check_id}
                </td>
                <td className="muted" style={{ fontSize: "0.84rem" }}>
                  {criterion.description || criterion.check_description}
                </td>
                <td className="num">{criterion.weight}</td>
                <td className="num">{criterion.target ?? "--"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <References references={pillar.references} />
    </section>
  );
}

function IndexSection({ index }: { index: PillarGuideIndex }) {
  const accent = gradeColor(index.distribution?.median ?? null);
  return (
    <section className="card pillar-card" id={index.key} style={{ borderTop: `4px solid ${accent}` }}>
      <div className="pillar-head">
        <div>
          <h3 style={{ margin: 0 }}>{index.name}</h3>
          <div className="muted mono" style={{ fontSize: "0.78rem" }}>
            {index.key} · {index.dimensions.length} dimensions · scored outside the composite
          </div>
        </div>
      </div>

      <p className="pillar-headline">{index.headline}</p>
      <Spread spread={index.distribution} capValue={index.overrides[0]?.cap_value} />

      <h4>Why it is scored separately</h4>
      <Prose text={index.why_it_matters} className="muted" />

      <div className="omission">
        <h4 style={{ marginTop: 0 }}>If you leave this index out of the assessment</h4>
        <Prose text={index.if_unassessed} />
      </div>

      {index.overrides.map((override) => (
        <div className="banner" key={override.key} style={{ marginTop: "0.9rem" }}>
          <h3>
            Hard blocker · caps {index.key} at {override.cap_value}
          </h3>
          <p style={{ margin: "0 0 0.4rem" }}>{override.rationale}</p>
          <div className="muted mono" style={{ fontSize: "0.76rem" }}>
            fires when {override.check_id} {override.condition.replace(/_/g, " ")} {override.threshold}
          </div>
        </div>
      ))}

      <h4>Dimensions</h4>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Dimension</th>
              <th>What it asks</th>
              <th>Checks it reads</th>
              <th className="num">Weight</th>
            </tr>
          </thead>
          <tbody>
            {index.dimensions.map((dimension) => (
              <tr key={dimension.key}>
                <td>
                  <strong>{dimension.name}</strong>
                </td>
                <td className="muted" style={{ fontSize: "0.84rem" }}>
                  {dimension.description}
                </td>
                <td className="mono muted" style={{ fontSize: "0.74rem" }}>
                  {dimension.check_ids.join(", ")}
                </td>
                <td className="num">{dimension.weight}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default async function PillarsPage() {
  let guide;
  try {
    guide = await pillarGuide();
  } catch (error) {
    if (error instanceof ApiUnavailable) return <ApiDownNotice detail={error.message} />;
    throw error;
  }

  const composite = guide.pillars.filter((p) => p.scoring_mode === "composite" && p.weight > 0);
  const overlays = guide.pillars.filter((p) => !(p.scoring_mode === "composite" && p.weight > 0));
  const compositeBands = guide.grade_bands.filter((b) => b.scope === "composite");

  return (
    <>
      <div className="eyebrow">Academy</div>
      <h1>The scoring pillars, and why each one is there</h1>
      <p className="lede">
        A readiness score is eight measurements, not one opinion. This page is the reference for
        people new to AI adoption: what each pillar asks, why it matters more once machines rather
        than people consume the data, what an estate looks like when the pillar is weak — and what
        you give up by leaving it out of an assessment. The weights, targets and checks below are
        read live from rubric v{guide.rubric.version}, so this page cannot drift from what the engine
        applies.
      </p>

      <section className="grid cols-4" style={{ marginBottom: "1.2rem" }}>
        <div className="metric">
          <div className="eyebrow">Pillars</div>
          <strong>{guide.totals.pillars}</strong>
          <small>seven weighted into the composite, one overlay</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Criteria</div>
          <strong>{guide.totals.criteria}</strong>
          <small>each one an automated check</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Checks in the library</div>
          <strong>{guide.totals.registered_checks}</strong>
          <small>metadata only — no customer row is read</small>
        </div>
        <div className="metric">
          <div className="eyebrow">Organizations assessed here</div>
          <strong>{guide.totals.assessed_organisations}</strong>
          <small>the spread shown under each pillar</small>
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>{guide.intro.title}</h3>
        <Prose text={guide.intro.body} className="muted" />
        {guide.intro.reading_order?.length ? (
          <>
            <h4>A reading order, if this is new to you</h4>
            <ol className="muted" style={{ paddingLeft: "1.2rem", maxWidth: "84ch" }}>
              {guide.intro.reading_order.map((step) => (
                <li key={step} style={{ marginBottom: "0.3rem" }}>
                  {step}
                </li>
              ))}
            </ol>
          </>
        ) : null}
      </section>

      <h2>The eight pillars at a glance</h2>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Pillar</th>
              <th className="num">Weight</th>
              <th>The question it answers</th>
              <th className="num">Criteria</th>
              <th>Portfolio spread (min / median / max)</th>
              <th>Hard blocker</th>
            </tr>
          </thead>
          <tbody>
            {guide.pillars.map((pillar) => (
              <tr key={pillar.key}>
                <td>
                  <a href={`#${pillar.key}`} style={{ fontWeight: 650 }}>
                    {pillar.name}
                  </a>
                </td>
                <td className="num">
                  {pillar.weight > 0 ? `${(pillar.weight * 100).toFixed(0)}%` : "overlay"}
                </td>
                <td className="muted" style={{ fontSize: "0.84rem" }}>
                  {pillar.core_question}
                </td>
                <td className="num">{pillar.criteria.length}</td>
                <td className="num">
                  {pillar.distribution
                    ? `${pillar.distribution.min} / ${pillar.distribution.median} / ${pillar.distribution.max}`
                    : "not scored yet"}
                </td>
                <td>
                  {pillar.overrides.length ? (
                    <span className="mono" style={{ fontSize: "0.74rem", color: "var(--severity-critical)" }}>
                      caps at {pillar.overrides[0].cap_value}
                    </span>
                  ) : (
                    <span className="muted">none</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
          Weights are a judgement about consequence, not effort. They live in the rubric YAML and can
          be forked per industry or per client without touching the engine — see{" "}
          <Link href="/methodology">Methodology</Link> for the arithmetic they feed.
        </p>
      </section>

      <h2>The seven pillars inside the composite</h2>
      {composite.map((pillar) => (
        <PillarSection key={pillar.key} pillar={pillar} />
      ))}

      <h2>Scored separately, on purpose</h2>
      <p className="lede">
        RAG Readiness sits outside the composite weighting, and its evidence is re-cut — along with
        the agent evidence — into two overlay indices. A retrieval or agent programme is usually
        funded on its own, moves faster than the platform beneath it, and fails for reasons a
        blended average would hide.
      </p>
      {overlays.map((pillar) => (
        <PillarSection key={pillar.key} pillar={pillar} />
      ))}
      {guide.indices.map((index) => (
        <IndexSection key={index.key} index={index} />
      ))}

      <h2>How the pillars become a grade</h2>
      <section className="card table-scroll">
        <table>
          <thead>
            <tr>
              <th>Grade</th>
              <th className="num">Composite range</th>
              <th>What it means for an AI programme</th>
            </tr>
          </thead>
          <tbody>
            {compositeBands.map((band) => (
              <tr key={band.grade}>
                <td>
                  <strong style={{ color: gradeColor(band.min) }}>{band.grade}</strong>
                </td>
                <td className="num">
                  {band.min}–{band.max}
                </td>
                <td className="muted">{band.interpretation}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ marginBottom: 0, fontSize: "0.84rem" }}>
          A grade is a band, not a target. The useful question is never &quot;how do we get to
          AI-Ready&quot; but &quot;which pillar is capping us, and what is the cheapest evidence that
          would clear it&quot; — which is what the roadmap on each organization&apos;s page answers.
        </p>
      </section>

      <h2>Where to go next</h2>
      <section className="card">
        <ul style={{ paddingLeft: "1.1rem", marginBottom: 0 }}>
          <li style={{ marginBottom: "0.4rem" }}>
            <Link href="/methodology">Methodology</Link> — the same rubric, worked end to end through
            one organization&apos;s evidence: a single check, a pillar&apos;s arithmetic, the
            composite, and what was not measured.
          </li>
          <li style={{ marginBottom: "0.4rem" }}>
            <Link href="/">Organizations</Link> — the assessed portfolio. Comparing two estates in the
            same industry is the fastest way to see what a pillar is actually detecting.
          </li>
          <li style={{ marginBottom: "0.4rem" }}>
            <Link href="/connectors">Connectors</Link> — what EAIRN reads to produce this evidence,
            and the exact least-privilege grants it asks for.
          </li>
        </ul>
      </section>

      <section className="card mono muted">
        <div>
          pillar guide v{guide.guide_version} · rubric v{guide.rubric.version} — {guide.rubric.name}
        </div>
        <div style={{ wordBreak: "break-all" }}>guide_digest: {guide.guide_digest}</div>
        <div>
          Weights, questions, targets and checks are read from the rubric tables; the explanations and
          references are versioned alongside them in the guide. Neither can change the other.
        </div>
      </section>
    </>
  );
}
