"use client";

import { useActionState, useEffect, useState } from "react";
import { runDemoAction, type DemoActionState } from "@/app/demo/actions";
import type { DemoOption, DemoOptions, DemoOrganisation } from "@/lib/api";

/** The pipeline the run actually executes, in the order it executes it. */
const STAGES = [
  { label: "Connect", detail: "Provisioning the synthetic estate to your configuration" },
  { label: "Harvest", detail: "Reading catalog, policy, lineage, quality and AI-surface metadata" },
  { label: "Evaluate", detail: "Running 53 checks; each emits evidence with a confidence tier" },
  { label: "Score", detail: "Applying rubric v2.0 — weighted means, then hard-blocker caps" },
  { label: "Benchmark", detail: "Comparing to the anonymised peer cohort for the industry" },
  { label: "Recommend", detail: "Simulating each play by re-running the engine with its target" },
  { label: "Freeze", detail: "Hashing rubric version + evidence + scores into a snapshot" },
];

function Field({
  label,
  name,
  options,
  defaultValue,
  hint,
}: {
  label: string;
  name: string;
  options: DemoOption[];
  defaultValue: string;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select name={name} defaultValue={defaultValue}>
        {options.map((option) => (
          <option key={option.key} value={option.key}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

/** Sentinel for "not one of the assessed organizations — I'll type a name". */
const NEW_ORGANISATION = "__new__";

export function DemoConsole({ options }: { options: DemoOptions }) {
  const [state, formAction, isPending] = useActionState<DemoActionState, FormData>(runDemoAction, {
    error: null,
  });
  const [stage, setStage] = useState(0);

  const defaults = options.defaults;
  const inIndustry = (industry: string) =>
    options.organisations.filter((org) => org.industry === industry);

  // Industry first, then the organizations actually in it, then the size band.
  const [industry, setIndustry] = useState(defaults.industry);
  const [orgKey, setOrgKey] = useState(
    () => inIndustry(defaults.industry)[0]?.key ?? NEW_ORGANISATION,
  );
  const [sizeBand, setSizeBand] = useState(
    () => inIndustry(defaults.industry)[0]?.size_band ?? defaults.size_band,
  );

  const organisations = inIndustry(industry);
  const selectedOrg: DemoOrganisation | undefined = organisations.find((o) => o.key === orgKey);

  const chooseIndustry = (next: string) => {
    setIndustry(next);
    // The organization list is industry-scoped, so the selection has to move
    // with it -- otherwise the form would submit a name from another industry.
    const first = inIndustry(next)[0];
    setOrgKey(first?.key ?? NEW_ORGANISATION);
    setSizeBand(first?.size_band ?? defaults.size_band);
  };

  const chooseOrganisation = (key: string) => {
    setOrgKey(key);
    const org = organisations.find((o) => o.key === key);
    // Prefill the band the organization is actually assessed at; the audience
    // can still change it, which is the point of asking.
    if (org) setSizeBand(org.size_band);
  };

  useEffect(() => {
    if (!isPending) {
      setStage(0);
      return;
    }
    // The run is fast; the stages are shown at a readable pace and hold on the
    // last one rather than pretending to finish before the server has.
    const timer = setInterval(
      () => setStage((current) => Math.min(current + 1, STAGES.length - 1)),
      420,
    );
    return () => clearInterval(timer);
  }, [isPending]);

  return (
    <form action={formAction} className="demo-form">
      <section className="card">
        <h3 style={{ marginTop: 0 }}>1 · Industry and organization</h3>
        <div className="field-grid">
          <label className="field">
            <span className="field-label">Industry</span>
            <select
              name="industry"
              value={industry}
              onChange={(event) => chooseIndustry(event.target.value)}
            >
              {options.industries.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="field-hint">
              Decides business domains and where regulated data sits — and which organizations you
              can pick next
            </span>
          </label>

          <label className="field">
            <span className="field-label">Organization</span>
            <select
              value={orgKey}
              onChange={(event) => chooseOrganisation(event.target.value)}
              name={orgKey === NEW_ORGANISATION ? undefined : "organisation_key"}
            >
              {organisations.map((org) => (
                <option key={org.key} value={org.key}>
                  {org.name}
                  {org.composite_score != null ? ` — ${org.composite_score.toFixed(1)} ${org.grade}` : ""}
                  {org.is_demo && !org.name.includes("(demo run)") ? " (demo run)" : ""}
                </option>
              ))}
              <option value={NEW_ORGANISATION}>Another organization — enter a name…</option>
            </select>
            <span className="field-hint">
              {organisations.length
                ? `${organisations.length} assessed in this industry`
                : "None assessed in this industry yet"}
            </span>
          </label>

          <label className="field">
            <span className="field-label">Size band</span>
            <select
              name="size_band"
              value={sizeBand}
              onChange={(event) => setSizeBand(event.target.value)}
            >
              {options.size_bands.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="field-hint">
              {selectedOrg
                ? `Assessed as ${selectedOrg.size_band.replace(/_/g, " ")} — change it to see the other cohort`
                : "Selects the peer cohort for benchmarking"}
            </span>
          </label>
        </div>

        {orgKey === NEW_ORGANISATION ? (
          <label className="field" style={{ marginTop: "0.9rem", maxWidth: "26rem" }}>
            <span className="field-label">Organization name</span>
            <input
              type="text"
              name="organisation"
              defaultValue={defaults.organisation}
              maxLength={120}
              required
              autoFocus
            />
            <span className="field-hint">Appears on every view of the result</span>
          </label>
        ) : (
          <>
            <input type="hidden" name="organisation" value={selectedOrg?.name ?? ""} />
            {selectedOrg ? (
              <p className="muted" style={{ fontSize: "0.84rem", margin: "0.7rem 0 0" }}>
                <strong>{selectedOrg.name}</strong> scores{" "}
                {selectedOrg.composite_score?.toFixed(1) ?? "--"} today ({selectedOrg.grade}). This
                run assesses a fresh estate under that name and lands as its own demo result — the
                organization&apos;s existing assessment is left exactly as it is.
              </p>
            ) : null}
          </>
        )}
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>2 · The platform and tooling</h3>
        <div className="field-grid">
          <Field
            label="Enterprise data platform"
            name="platform"
            options={options.platforms}
            defaultValue={defaults.platform}
            hint="Where the datasets, grants and policies live"
          />
          <Field
            label="Data governance tool"
            name="governance_tool"
            options={options.governance_tools}
            defaultValue={defaults.governance_tool}
            hint="Catalog, glossary and certification workflow"
          />
          <Field
            label="Data quality tooling"
            name="dq_tool"
            options={options.dq_tools}
            defaultValue={defaults.dq_tool}
            hint="Where DQ rules and incidents are recorded"
          />
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>3 · How far the programme has got</h3>
        <div className="field-grid">
          <Field
            label="Governance maturity"
            name="maturity"
            options={options.maturities}
            defaultValue={defaults.maturity}
            hint="Sets coverage rates, never a score"
          />
          <label className="field">
            <span className="field-label">Seed</span>
            <input type="number" name="seed" defaultValue={defaults.seed} min={1} max={99999999} />
            <span className="field-hint">Same seed and options reproduce this estate exactly</span>
          </label>
        </div>

        <h4 className="field-label" style={{ marginTop: "1rem" }}>
          Assessment scope — leave a surface out and its checks report as not measured
        </h4>
        <div className="scope-grid">
          {options.scopes.map((scope) => (
            <label className="scope" key={scope.key}>
              <input type="checkbox" name="scopes_off" value={scope.key} />
              <span>
                <strong>Skip {scope.label.toLowerCase()}</strong>
                <span className="field-hint">{scope.note}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="muted" style={{ fontSize: "0.82rem", margin: "0.6rem 0 0" }}>
          Skipping a surface does not score it as zero. The checks that read it are reported as
          unmeasured, and the coverage gap is carried into the action plan — which is exactly what a
          real estate without that surface produces.
        </p>
      </section>

      {state.error ? (
        <div className="banner">
          <h3>The run did not complete</h3>
          <p style={{ margin: 0 }}>{state.error}</p>
        </div>
      ) : null}

      <div className="run-bar">
        <button type="submit" className="run-button" disabled={isPending}>
          {isPending ? "Running evaluation…" : "Run evaluation now"}
        </button>
        <span className="muted" style={{ fontSize: "0.84rem" }}>
          Generates the estate, runs all 53 checks, scores it under rubric v2.0 and freezes a
          verifiable snapshot. Typically about a second.
        </span>
      </div>

      {isPending ? (
        <section className="card runner" aria-live="polite">
          <h3 style={{ marginTop: 0 }}>Assessment in progress</h3>
          <ol className="stages">
            {STAGES.map((item, index) => (
              <li
                key={item.label}
                className={index < stage ? "done" : index === stage ? "active" : ""}
              >
                <span className="stage-name">{item.label}</span>
                <span className="stage-detail">{item.detail}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </form>
  );
}
