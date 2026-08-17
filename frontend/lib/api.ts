/**
 * Server-side API client for the EAIRN backend.
 *
 * Every call is `no-store`: the Portal renders live snapshot state, and a
 * cached readiness score is a wrong readiness score.
 */

const BASE_URL = process.env.EAIRN_API_URL ?? "http://127.0.0.1:8000";

export class ApiUnavailable extends Error {
  constructor(readonly path: string, readonly cause: unknown) {
    super(`EAIRN API unreachable at ${BASE_URL}${path}`);
  }
}

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { cache: "no-store" });
  } catch (error) {
    throw new ApiUnavailable(path, error);
  }
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as T;
}

// -- types (only the fields the Portal renders) ------------------------------ //

export interface AssessmentSummary {
  snapshot_id: string;
  tenant: string | null;
  tenant_key: string | null;
  label: string;
  status: string;
  rubric_version: string;
  harvested_at: string | null;
  frozen_at: string | null;
  snapshot_hash: string | null;
  composite_score: number | null;
  grade: string | null;
  ari_score: number | null;
  ari_grade: string | null;
  rri_score: number | null;
  rri_grade: string | null;
  stats: Record<string, any>;
}

export interface ScoreLine {
  scope: string;
  key: string;
  parent_key: string | null;
  name: string;
  score: number;
  raw_score: number;
  weight: number;
  grade: string | null;
  capped_by: string | null;
  evidence_ids: number[];
}

export interface EvidenceRecord {
  id: number;
  check_id: string;
  check_title: string;
  pillar_key: string;
  platform: string;
  domain: string | null;
  target_urn: string;
  result: number;
  measured: Record<string, unknown>;
  confidence: number;
  rationale: string;
  severity: string;
  status: string;
  failing_target_count: number;
  failing_targets?: string[];
  reviewed_by: string | null;
}

export interface Recommendation {
  id: number;
  playbook_id: string;
  title: string;
  pillar_key: string;
  horizon: string;
  summary: string;
  steps: string[];
  effort_days: number;
  cost_estimate: number;
  composite_impact: number;
  unblocks: string[];
  confidence: number;
  rationale: string;
  evidence_ids: number[];
  status: string;
}

export interface Benchmark {
  metric_key: string;
  /** Display name from the rubric, e.g. "Agent Readiness Index" for key "ARI". */
  label?: string;
  score: number;
  percentile: number;
  cohort_key: string;
  cohort_definition: { industry: string; size_band: string; platform_mix: string; n: number };
  distribution: { p25: number; p50: number; p75: number; p90: number };
  reliable: boolean;
}

export interface Cap {
  override: string;
  scope: string;
  check_id: string;
  cap_value: number;
  uncapped_score: number;
  rationale: string;
  failing_targets: number;
  /** False when the estate already scores below the cap: the finding stands,
   *  but there is nothing left for it to cap. */
  applied?: boolean;
}

export interface PortfolioOrg {
  tenant_key: string;
  tenant: string;
  size_band: string;
  snapshot_id: string;
  label: string;
  harvested_at: string | null;
  composite_score: number | null;
  grade: string | null;
  grade_interpretation: string;
  ari_score: number | null;
  ari_grade: string | null;
  rri_score: number | null;
  rri_grade: string | null;
  hard_blockers: number;
  hard_blockers_binding: number;
  evidence_records: number;
  assessment_count: number;
}

export interface PortfolioIndustry {
  industry: string;
  industry_label: string;
  organisations: PortfolioOrg[];
  median_composite: number | null;
}

export interface ExecutiveView {
  assessment: AssessmentSummary;
  industry: string | null;
  industry_label: string | null;
  grade_interpretation: string;
  pillars: ScoreLine[];
  indices: ScoreLine[];
  benchmarks: Benchmark[];
  trend: { snapshot_id: string; harvested_at: string | null; composite_score: number | null; grade: string | null }[];
  caps_applied: Cap[];
  top_risks: EvidenceRecord[];
  roadmap: {
    horizon: string;
    label: string;
    effort_days: number;
    cost_estimate: number;
    projected_impact: number;
    cumulative_impact: number;
    recommendations: Recommendation[];
  }[];
  investment: { total_effort_days: number; total_cost_estimate: number; projected_composite: number };
  advisor_narrative: {
    body: string;
    citations: number[];
    generator: string;
    model: string | null;
    confidence: number;
    status: string;
    cited_evidence: EvidenceRecord[];
  } | null;
}

export interface ArchitectView {
  assessment: AssessmentSummary;
  scores: ScoreLine[];
  heatmap_by_platform: { key: string; pillars: Record<string, number> }[];
  heatmap_by_domain: { key: string; pillars: Record<string, number> }[];
  criteria: (ScoreLine & { evidence: EvidenceRecord[] })[];
  unmeasured_criteria: string[];
  checks_skipped: string[];
}

export interface StewardView {
  assessment: AssessmentSummary;
  review_queue: EvidenceRecord[];
  findings_queue: EvidenceRecord[];
  draft_recommendations: Recommendation[];
  workload: { pending_review: number; open_findings: number; failing_targets: number };
}

// -- methodology ------------------------------------------------------------ //

export interface MethodologyCriterion {
  key: string;
  name: string;
  check_id: string;
  check_title: string;
  description: string;
  check_description: string;
  target: number | null;
  weight: number;
  measured: boolean;
  score: number | null;
  contribution: number | null;
  evidence_count: number;
  evidence: (EvidenceRecord & { measured: Record<string, unknown>; failing_sample: string[] })[];
}

export interface MethodologyPillar {
  key: string;
  name: string;
  weight: number;
  scoring_mode: string;
  core_question: string;
  rationale: string;
  criteria: MethodologyCriterion[];
  weighted_numerator: number | null;
  weight_denominator: number | null;
  criteria_weight_total: number | null;
  unmeasured_weight_share: number | null;
  recomputed_raw: number | null;
  engine_raw: number | null;
  reconciles: boolean;
  score: number | null;
  grade: string | null;
  capped_by: string | null;
  cap: Cap | null;
  contribution_to_composite: number | null;
  unmeasured_criteria: string[];
}

export interface GradeBand {
  grade: string;
  min: number;
  max: number;
  interpretation: string;
}

export interface MethodologyComposite {
  terms: { key: string; name: string; score: number; weight: number; contribution: number; capped_by: string | null }[];
  weighted_numerator: number | null;
  weight_denominator: number | null;
  recomputed_raw: number | null;
  engine_raw: number | null;
  reconciles: boolean;
  score: number | null;
  grade: string | null;
  capped_by: string | null;
  cap: Cap | null;
  bands: GradeBand[];
}

export interface MethodologyIndex {
  key: string;
  name: string;
  dimensions: {
    key: string;
    name: string;
    weight: number;
    description: string;
    check_ids: string[];
    score: number | null;
    contribution: number | null;
  }[];
  weighted_numerator: number | null;
  weight_denominator: number | null;
  recomputed_raw: number | null;
  engine_raw: number | null;
  reconciles: boolean;
  score: number | null;
  grade: string | null;
  capped_by: string | null;
  cap: Cap | null;
  bands: GradeBand[];
}

export interface MethodologySample {
  datasets: {
    urn: string;
    name: string;
    domain: string | null;
    tier: number;
    platform: string;
    owner: string | null;
    owner_verified: boolean;
    certified: boolean;
    curated: boolean;
    described: boolean;
    description: string;
    column_count: number;
    columns: {
      name: string;
      data_type: string;
      classification: string | null;
      described: boolean;
      protected: boolean;
      protection_kind: string | null;
    }[];
  }[];
  policies: { policy_type: string; name: string; platform: string; bound_to_tag: string | null; target_count: number; targets: string[] }[];
  grants: { grantee: string; grantee_type: string; privilege: string; object_urn: string; is_admin_role: boolean }[];
  dq_monitors: { dataset_urn: string; tool: string; check_type: string; defined_as_data: boolean; enabled: boolean; pass_rate: number | null }[];
  ml_assets: { name: string; kind: string; registered: boolean; training_data_lineage: boolean; promotion_gated: boolean }[];
  semantic_models: { name: string; platform: string; certified: boolean; field_count: number; described_field_count: number }[];
  agents: { name: string; identity_kind: string; scoped_roles: boolean; write_actions: boolean; write_approval_gate: boolean; action_audit: boolean }[];
  rag_corpora: { name: string; source_system: string; authoritative_doc_count: number; indexed_doc_count: number; acl_propagated: boolean; citation_enforced: boolean }[];
}

export interface MethodologyView {
  default_snapshot: string;
  requested_snapshot: string | null;
  assessment: AssessmentSummary;
  industry: string | null;
  industry_label: string | null;
  size_band: string | null;
  rubric: {
    version: string;
    name: string;
    confidence_threshold: number;
    source_digest: string;
    index_names: Record<string, string>;
  };
  provenance: {
    connectors: {
      connector: string;
      config: Record<string, any>;
      capabilities: string[];
      warnings: string[];
      counts: Record<string, number>;
    }[];
    sample_matches_snapshot: boolean;
    sample: MethodologySample | null;
  };
  evidence_totals: {
    records: number;
    accepted: number;
    pending_review: number;
    rejected: number;
    checks_with_evidence: number;
    registered_checks: number;
    context_records: number;
    failing_targets: number;
  };
  pillars: MethodologyPillar[];
  composite: MethodologyComposite;
  indices: MethodologyIndex[];
  overrides: {
    key: string;
    check_id: string;
    condition: string;
    threshold: number;
    cap_scope: string;
    cap_value: number;
    rationale: string;
    fired: boolean;
    applied: boolean;
    failing_targets: number | null;
  }[];
  confidence: {
    threshold: number;
    tiers: { key: string; value: number; label: string; meaning: string; example: string; scored: boolean }[];
  };
  coverage: {
    unmeasured_criteria: {
      key: string;
      name: string;
      pillar: string;
      pillar_key?: string;
      check_id: string;
      weight?: number;
      missing_capabilities?: string[];
      status?: "missing_capability" | "held_for_review" | "nothing_to_measure";
      evidence_records?: number;
      why: string;
    }[];
    checks_skipped: { check_id: string; title: string; pillar_key: string; requires: string[]; missing_capabilities: string[] }[];
    pending_review: EvidenceRecord[];
    capabilities_present: string[];
    capabilities_absent: string[];
    never_collected: { item: string; why: string }[];
    composite_weight_unmeasured: number;
    by_pillar: { key: string; name: string; unmeasured_weight_share: number; unmeasured_criteria: string[] }[];
  };
  settings: { row_sampling_enabled: boolean };
}

export interface ConnectorDescriptor {
  key: string;
  platform: string;
  display_name: string;
  capabilities: string[];
  roadmap_phase: string;
  live_harvest_available: boolean;
  accepts_canonical_bundle: boolean;
  query_catalog: string[];
  api_catalog: string[];
  permission_manifest: {
    principal: string;
    reads_row_data: boolean;
    notes: string;
    grants: { scope: string; grant: string; purpose: string }[];
  };
}

// -- calls ------------------------------------------------------------------ //

export const portfolio = () =>
  get<{ industries: PortfolioIndustry[] }>("/api/portfolio").then((r) => r.industries);

/**
 * Locate one assessed estate by snapshot id, together with the industry it sits
 * in. Every estate page is addressed by its own snapshot, so there is no
 * "default estate" to fall back to: an unknown snapshot is a 404, not somebody
 * else's numbers rendered under the wrong name.
 */
export const findOrg = async (
  snapshotId: string,
): Promise<{ org: PortfolioOrg; industry: PortfolioIndustry } | null> => {
  const industries = await portfolio();
  for (const industry of industries) {
    const org = industry.organisations.find((o) => o.snapshot_id === snapshotId);
    if (org) return { org, industry };
  }
  return null;
};

export const listAssessments = () =>
  get<{ assessments: AssessmentSummary[] }>("/api/assessments").then((r) => r.assessments);

export const latestSnapshotId = async (): Promise<string | null> => {
  const assessments = await listAssessments();
  return assessments[0]?.snapshot_id ?? null;
};

export const executiveView = (snapshotId: string) =>
  get<ExecutiveView>(`/api/assessments/${snapshotId}/dashboard/executive`);

export const architectView = (snapshotId: string) =>
  get<ArchitectView>(`/api/assessments/${snapshotId}/dashboard/architect`);

export const stewardView = (snapshotId: string) =>
  get<StewardView>(`/api/assessments/${snapshotId}/dashboard/steward`);

export const methodology = (snapshotId?: string) =>
  get<MethodologyView>(
    snapshotId ? `/api/methodology?snapshot=${encodeURIComponent(snapshotId)}` : "/api/methodology",
  );

export const connectors = () =>
  get<{ connectors: ConnectorDescriptor[] }>("/api/connectors").then((r) => r.connectors);

export const evidenceDetail = (evidenceId: string) =>
  get<EvidenceRecord>(`/api/evidence/${evidenceId}`);

export const verifySnapshot = (snapshotId: string) =>
  get<{ reproducible: boolean; recorded_hash: string; replayed_hash: string }>(
    `/api/assessments/${snapshotId}/verify`,
  );
