"use server";

import { redirect } from "next/navigation";
import { ApiUnavailable, runDemo } from "@/lib/api";

export interface DemoActionState {
  error: string | null;
}

/**
 * Run one live-demo assessment, then land on the estate it produced.
 *
 * The browser never talks to the assessment API directly: the form posts here,
 * the server calls the backend, and the redirect carries the snapshot id. That
 * keeps the API surface server-side and means the demo works unchanged when the
 * backend is not reachable from the viewer's network.
 */
export async function runDemoAction(
  _previous: DemoActionState,
  formData: FormData,
): Promise<DemoActionState> {
  const scopesOff = formData.getAll("scopes_off").map(String);
  let snapshotId: string;

  try {
    const result = await runDemo({
      organisation: String(formData.get("organisation") ?? "").trim(),
      industry: String(formData.get("industry") ?? "financial_services"),
      platform: String(formData.get("platform") ?? "snowflake"),
      governance_tool: String(formData.get("governance_tool") ?? "collibra"),
      dq_tool: String(formData.get("dq_tool") ?? "monte_carlo"),
      maturity: String(formData.get("maturity") ?? "emerging"),
      size_band: String(formData.get("size_band") ?? "enterprise"),
      seed: Number(formData.get("seed") ?? 20260817),
      scopes_off: scopesOff,
    });
    snapshotId = result.snapshot_id;
  } catch (error) {
    if (error instanceof ApiUnavailable) {
      return { error: `${error.message} — start the backend and try again.` };
    }
    return { error: error instanceof Error ? error.message : "The demo run failed." };
  }

  // Outside the try: redirect() signals by throwing, and catching it here would
  // turn a successful run into an error message.
  redirect(`/estates/${snapshotId}?from=demo`);
}
