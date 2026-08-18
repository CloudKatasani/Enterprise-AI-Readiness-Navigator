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
  /** Harvest runs behind this snapshot, with their non-secret provenance. */
  connectors?: { connector: string; harvest_run_id: number; stats: Record<string, any> }[];
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

// -- live demo -------------------------------------------------------------- //

export interface DemoOption {
  key: string;
  label: string;
  note: string;
}

/** One assessed organization, as the Organizations tab lists it. */
export interface DemoOrganisation {
  key: string;
  name: string;
  industry: string;
  industry_label: string;
  size_band: string;
  composite_score: number | null;
  grade: string | null;
  is_demo: boolean;
}

export interface DemoOptions {
  organisations: DemoOrganisation[];
  platforms: DemoOption[];
  governance_tools: DemoOption[];
  dq_tools: DemoOption[];
  scopes: DemoOption[];
  size_bands: DemoOption[];
  industries: DemoOption[];
  maturities: DemoOption[];
  defaults: {
    organisation: string;
    industry: string;
    platform: string;
    governance_tool: string;
    dq_tool: string;
    maturity: string;
    size_band: string;
    seed: number;
    scopes_off: string[];
  };
  advisor: "model" | "template";
  synthetic: boolean;
}

export interface DemoRunRequest {
  organisation: string;
  industry: string;
  platform: string;
  governance_tool: string;
  dq_tool: string;
  maturity: string;
  size_band: string;
  seed: number;
  scopes_off: string[];
}

export interface DemoRunResult {
  snapshot_id: string;
  tenant_key: string;
  tenant: string;
  composite_score: number | null;
  grade: string | null;
  ari_score: number | null;
  rri_score: number | null;
  snapshot_hash: string | null;
  stats: Record<string, any>;
  configuration: Record<string, any>;
}

// -- action plan ------------------------------------------------------------ //

export interface ActionPlayRef extends Recommendation {}

export interface ActionBlocker extends Cap {
  check_title: string;
  current_result: number | null;
  failing_sample: string[];
  failing_total: number;
  plays: ActionPlayRef[];
  owner: string;
}

export interface ArchitectAction {
  kind: "below_target" | "no_coverage";
  criterion_key: string;
  criterion: string;
  pillar_key: string;
  pillar: string;
  check_id: string;
  check_description: string;
  score: number | null;
  target: number | null;
  shortfall: number | null;
  priority: number;
  pillar_capped_by?: string | null;
  requires?: string[];
  failing_total: number;
  failing_sample: string[];
  plays: ActionPlayRef[];
  owner: string;
}

export interface StewardAction {
  kind: "decide" | "remediate";
  evidence_id: number;
  check_id: string;
  check_title: string;
  pillar_key: string;
  severity?: string;
  result: number;
  confidence: number;
  rationale: string;
  failing_total: number;
  failing_sample: string[];
  owner: string;
  action: string;
}

export interface ActionPlanView {
  assessment: AssessmentSummary;
  blockers: ActionBlocker[];
  architect_actions: ArchitectAction[];
  steward_actions: StewardAction[];
  horizons: {
    horizon: string;
    label: string;
    effort_days: number;
    cost_estimate: number;
    projected_impact: number;
    cumulative_impact: number;
    projected_composite: number;
    projected_grade: string;
    recommendations: Recommendation[];
  }[];
  projection: {
    current_composite: number;
    current_grade: string | null;
    projected_composite: number;
    projected_grade: string;
    total_effort_days: number;
    total_cost_estimate: number;
  };
  summary: {
    blockers: number;
    blockers_binding: number;
    architect_actions: number;
    architect_below_target: number;
    coverage_gaps: number;
    steward_decisions: number;
    steward_remediations: number;
    failing_objects: number;
  };
}

// -- scoring pillars (academy) ---------------------------------------------- //

export interface PillarReference {
  title: string;
  source: string;
  url?: string;
  note?: string;
}

export interface PillarSpread {
  n: number;
  min: number;
  median: number;
  max: number;
}

export interface PillarOverride {
  key: string;
  check_id: string;
  condition: string;
  threshold: number;
  cap_value: number;
  rationale: string;
}

export interface PillarGuideCriterion {
  key: string;
  name: string;
  check_id: string;
  check_title: string;
  check_description: string;
  weight: number;
  target: number | null;
  description: string;
}

export interface PillarGuideEntry {
  key: string;
  name: string;
  weight: number;
  scoring_mode: string;
  core_question: string;
  rubric_rationale: string;
  criteria: PillarGuideCriterion[];
  overrides: PillarOverride[];
  distribution: PillarSpread | null;
  headline: string;
  why_it_matters: string;
  ai_impact: string;
  without_it: string[];
  if_unassessed: string;
  good_looks_like: string[];
  references: PillarReference[];
}

export interface PillarGuideIndex {
  key: string;
  name: string;
  dimensions: { key: string; name: string; weight: number; description: string; check_ids: string[] }[];
  overrides: PillarOverride[];
  distribution: PillarSpread | null;
  headline: string;
  why_it_matters: string;
  if_unassessed: string;
}

export interface PillarGuideView {
  guide_version: string;
  guide_digest: string;
  rubric: { version: string; name: string; confidence_threshold: number };
  intro: { title: string; body: string; reading_order: string[] };
  pillars: PillarGuideEntry[];
  indices: PillarGuideIndex[];
  grade_bands: { scope: string; grade: string; min: number; max: number; interpretation: string }[];
  totals: {
    pillars: number;
    criteria: number;
    registered_checks: number;
    assessed_organisations: number;
  };
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
  agents: {
    name: string;
    identity_kind: string;
    scoped_roles: boolean;
    write_actions: boolean;
    write_approval_gate: boolean;
    action_audit: boolean;
    replayable_trail: boolean;
  }[];
  rag_corpora: {
    name: string;
    source_system: string;
    authoritative_doc_count: number;
    indexed_doc_count: number;
    acl_propagated: boolean;
    retrieval_filter_enforced: boolean;
    contains_classified: boolean;
    citation_enforced: boolean;
  }[];
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

export const pillarGuide = () => get<PillarGuideView>("/api/pillars");

export const demoOptions = () => get<DemoOptions>("/api/demo/options");

export const actionPlan = (snapshotId: string) =>
  get<ActionPlanView>(`/api/assessments/${snapshotId}/action-plan`);

/** Run one live-demo assessment. Only called from a server action. */
export const runDemo = async (body: DemoRunRequest): Promise<DemoRunResult> => {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/demo/run`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch (error) {
    throw new ApiUnavailable("/api/demo/run", error);
  }
  if (!response.ok) {
    throw new Error(`demo run failed: ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as DemoRunResult;
};

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

// -- API documentation ------------------------------------------------------ //

export interface IntegrationCall {
  name: string;
  kind: "sql" | "http";
  method?: string;
  statement: string;
  read_only_verified: boolean;
  reviewed_read_only_post?: boolean;
}

export interface IntegrationAuthMode {
  mode: string;
  recommended?: boolean;
  detail: string;
}

export interface IntegrationConfigField {
  key: string;
  required: boolean;
  secret: boolean;
  example: string;
  detail: string;
}

export interface IntegrationEgress {
  host: string;
  port: number;
  detail: string;
}

export interface IntegrationCoverage {
  unlocked_count: number;
  blocked_count: number;
  by_pillar: {
    pillar_key: string;
    pillar_name: string;
    checks: { check_id: string; title: string }[];
  }[];
  still_unmeasured: { check_id: string; title: string; missing: string[] }[];
}

export interface IntegrationConnector {
  key: string;
  platform: string;
  display_name: string;
  capabilities: string[];
  roadmap_phase: string;
  live_harvest_available: boolean;
  accepts_canonical_bundle: boolean;
  live_driver: string;
  permission_manifest: {
    principal: string;
    reads_row_data: boolean;
    notes: string;
    grants: { scope: string; grant: string; purpose: string }[];
  };
  calls: IntegrationCall[];
  read_only_problems: string[];
  coverage: IntegrationCoverage;
  summary: string;
  vendor_docs: { title: string; url: string }[];
  auth: IntegrationAuthMode[];
  config_fields: IntegrationConfigField[];
  egress: IntegrationEgress[];
  freshness: string;
  pagination: string;
  limits: string;
  preconditions: string[];
  documented: boolean;
}

export interface IntegrationView {
  guide_version: string;
  guide_digest: string;
  intro: { headline: string; body: string };
  hosting: {
    summary: string;
    runtime: { name: string; detail: string }[];
    secrets: { platform: string; service: string; detail: string }[];
    network: { summary: string; notes: string[] };
    environment: {
      intro: string;
      variables: { name: string; example: string; detail: string; current?: string }[];
    };
    sequence: { step: string; detail: string }[];
  };
  canonical_bundle: {
    summary: string;
    why: string;
    fields: { entity: string; detail: string }[];
    configuration: string;
  };
  connectors: IntegrationConnector[];
  capability_matrix: {
    capability: string;
    connectors: string[];
    checks: { check_id: string; pillar_key: string; pillar_name: string }[];
    check_count: number;
  }[];
  totals: {
    connectors: number;
    live_drivers: number;
    bundle_backed: number;
    documented_calls: number;
    registered_checks: number;
    read_only_violations: number;
  };
}

// -- data model ------------------------------------------------------------- //

export interface DataModelColumn {
  name: string;
  type: string;
  postgres_type: string;
  nullable: boolean;
  primary_key: boolean;
  foreign_keys: string[];
  indexed: boolean;
  unique: boolean;
  has_default: boolean;
}

export interface DataModelTable {
  name: string;
  class_name: string;
  purpose: string;
  populated_by_capability: string | null;
  columns: DataModelColumn[];
  primary_key: string[];
  foreign_keys: [string, string, string][];
  unique_constraints: { name: string; columns: string[] }[];
  indexes: { name: string; columns: string[]; unique: boolean }[];
  postgres_ddl: string;
  row_count: number | null;
}

export interface DataModelFamily {
  key: string;
  name: string;
  lifecycle: string;
  summary: string;
  tables: DataModelTable[];
}

export interface DataModelView {
  families: DataModelFamily[];
  relationships: {
    from_table: string;
    from_column: string;
    to_table: string;
    to_column: string;
    on_delete: string;
  }[];
  deployment: {
    current_dialect: string;
    current_url: string;
    is_production_target: boolean;
    targets: { platform: string; service: string; url: string; detail: string }[];
    notes: { heading: string; body: string }[];
  };
  totals: {
    tables: number;
    columns: number;
    foreign_keys: number;
    indexes: number;
    registered_checks: number;
    rows: number | null;
  };
}

export const integrationGuide = () => get<IntegrationView>("/api/integration");

export const dataModel = () => get<DataModelView>("/api/data-model");
