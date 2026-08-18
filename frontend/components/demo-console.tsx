"use client";

import { useActionState, useEffect, useState } from "react";
import { runDemoAction, type DemoActionState } from "@/app/demo/actions";
import type { DemoOption, DemoOptions } from "@/lib/api";

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

export function DemoConsole({ options }: { options: DemoOptions }) {
  const [state, formAction, isPending] = useActionState<DemoActionState, FormData>(runDemoAction, {
    error: null,
  });
  const [stage, setStage] = useState(0);

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

  const defaults = options.defaults;

  return (
    <form action={formAction} className="demo-form">
      <section className="card">
        <h3 style={{ marginTop: 0 }}>1 · The organization</h3>
        <div className="field-grid">
          <label className="field">
            <span className="field-label">Organization name</span>
            <input
              type="text"
              name="organisation"
              defaultValue={defaults.organisation}
              maxLength={120}
              required
            />
            <span className="field-hint">Appears on every view of the result</span>
          </label>
          <Field
            label="Industry"
            name="industry"
            options={options.industries}
            defaultValue={defaults.industry}
            hint="Decides business domains and where regulated data sits"
          />
          <Field
            label="Size band"
            name="size_band"
            options={options.size_bands}
            defaultValue={defaults.size_band}
            hint="Selects the peer cohort for benchmarking"
          />
        </div>
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
