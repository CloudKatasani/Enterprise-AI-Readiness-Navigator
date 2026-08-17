# EAIRN Architecture

Seven cooperating services, matching the blueprint's reference architecture. Inter-service contracts
are tool-neutral: the rubric, the playbook library and the cohort distributions are YAML loaded into
versioned tables, and every platform-specific artefact (SQL, API call) is a rendering of the canonical
model rather than a source of truth.

| Component | Module | Responsibility |
|---|---|---|
| Portal | `frontend/` | Role-scoped views: executive, architect, steward, connector permission pack |
| Connector Framework | `backend/eairn/connectors/` | Pluggable read-only adapters, each with a capability set and a published permission manifest |
| Metadata Engine | `backend/eairn/models.py`, `pipeline.py` | Canonical entity model and the harvest→persist path |
| Governance Engine | `backend/eairn/checks/governance.py`, `security.py` | Policy, classification, ownership and access posture, including mechanical propagation checks |
| Scoring Engine | `backend/eairn/scoring/` | Applies the versioned rubric to evidence; emits scores, grades, caps and the snapshot hash |
| Recommendation Engine | `backend/eairn/recommend/` | Maps findings to playbooks and measures each play's impact by simulation |
| AI Advisor | `backend/eairn/advisor/` | Executive narrative grounded strictly in one snapshot, with citations to evidence IDs |

---

## Data flow

```
1. Connect    provision a least-privilege principal per the connector's permission manifest
2. Harvest    connectors normalise platform metadata into the canonical model (no row data)
3. Evaluate   the check library runs; each check emits evidence with confidence and rationale
4. Score      the Scoring Engine applies the active rubric version; caps bind where triggered
5. Benchmark  composite, pillar and index scores compare to the anonymised peer cohort
6. Recommend  gaps map to playbooks; impact is measured by re-scoring, not estimated
7. Snapshot   rubric version + evidence + scores are frozen and hashed
```

Steps 2–7 are `eairn.pipeline.run_assessment`, which is also what `POST /api/assessments` calls.

---

## Canonical metadata model

Connectors normalise into one shape so a check is written once and works across platforms:

| Family | Entities |
|---|---|
| Structure | `Dataset` (tier, domain, owner, certification, governed flag), `Column` (classification from platform *and* catalog, protection) |
| Relationships | `LineageEdge` (table and column level, with source and confidence) |
| Control | `Policy` (masking, row access, redaction, policy tag), `Grant` |
| Behaviour | `UsageEvent` (daily rollup; never statement text) |
| Quality | `DQMonitor`, `DQIncident` |
| AI surface | `MLAsset`, `SemanticModel`, `KPIDefinition`, `AgentAsset`, `RAGCorpus` |
| Programme | `GovernanceProgram`, `QuestionnaireResponse`, `SamplingAuthorization` |

Nothing in this model can hold customer row data. The optional sampling module is a separate package
gated on `SamplingAuthorization` records.

---

## Scoring mechanics

```
criterion score  = aggregate of accepted evidence for its check_id
                   (weighted by measurement size when a check emits several records)
pillar score     = Σ(criterion × weight) / Σ(weight)   → then hard-blocker caps
composite        = Σ(pillar × weight) / Σ(weight)      → then composite-scope caps
index            = Σ(dimension × weight) / Σ(weight)   → then index-scope caps
                   (Agent Readiness Index, RAG Readiness Index; keyed ARI/RRI)
```

Three rules the engine enforces regardless of rubric content:

1. **Evidence below the confidence threshold never moves a score.** It is marked `pending_review` and
   excluded. A reviewer decision — recorded with their name and timestamp on the evidence row — is the
   only thing that overrides the threshold.
2. **A criterion with no evidence is unmeasured, not zero.** It is dropped from its pillar's denominator
   and reported in `stats.unmeasured_criteria`, alongside the checks skipped for missing connector
   capability.
3. **Tier weighting lives in the checks.** Tier-1 assets dominate the denominators, so a thousand
   hygienic sandbox tables cannot mask ungoverned crown jewels.

### Hard-blocker overrides

An override names a check, a condition, a scope and a cap value, and carries its own rationale — all
rubric data. When it triggers, the score row records both the capped value and the arithmetic value,
so the executive view can show what the estate *would* score once the blocker clears.

The engine records every override whose condition fires (`blockers_triggered`), and separately those
that actually lowered a score (`caps_applied`, and `applied: true` on the entry). The distinction
matters at the bottom of the range: an estate already scoring below a cap has nothing left to cap,
but the blocking finding is still there. Reporting only applied caps would show the weakest estates
as having no blockers at all.

### Index display names

`ARI` and `RRI` are keys. Their display names — Agent Readiness Index, RAG Readiness Index — are
rubric data (`indices.<key>.name`), stored on the rubric row and used for score names and benchmark
labels, so a forked rubric can rename an index without an engine change.

### Reproducibility

`snapshot_hash = sha256(rubric_version + sorted evidence tuples + sorted score lines)`.

`GET /api/assessments/{id}/verify` re-runs the engine over the frozen evidence and compares. The
golden tests assert the same property from the other direction: re-scoring an untouched snapshot must
be byte-identical, and the demo connector must produce identical output on every run.

---

## Confidence tiers

| Tier | Value | Used for |
|---|---|---|
| Declared | 1.00 | Read straight from a system catalog |
| Reconciled | 0.92 | Cross-checked between two sources (e.g. catalog vs platform classification) |
| Derived | 0.85 | Computed from declared facts (graph traversal, ratios over declared state) |
| Inferred | 0.70 | Heuristic inference — **below the default threshold**, so it queues for review |
| Self-reported | 0.60 | Questionnaire answer with no machine backing |

This is why name-pattern sensitivity detection (`SE-001`) and query-history-derived column lineage
(`MD-005`) land in the steward's queue rather than silently moving a score.

---

## Connector contract

```python
class Connector:
    def capabilities(self) -> set[str]:        # which canonical families this connector populates
    def permission_manifest(self) -> PermissionManifest:   # published to the customer verbatim
    def harvest(self) -> HarvestBundle:        # canonical entities; must not mutate anything
```

Every statement goes through `assert_read_only`, every API entry through `assert_read_only_api`, and
CI runs both across every registered connector. Live and fixture modes share one normaliser, so the
code path exercised by tests is the code path used against a live account.

---

## Extending EAIRN

**A new check:** add a function to `eairn/checks/`, decorate it with `@check(id, title=…, pillar=…,
requires={…})`, and add a criterion referencing its ID to the rubric YAML. `test_scoring_golden.py`
asserts that every rubric criterion maps to a registered check, so a mismatch fails CI.

**A new weighting profile:** copy `rubric_v2.0.yaml`, bump `version`, edit weights or bands, and load
it. Existing snapshots keep scoring against the version they were frozen under — a partner can
white-label a weighting profile without forking the engine.

**A new connector:** subclass `Connector`, declare capabilities and the permission manifest, publish
the query or API catalog, and register it. Bundle-backed connectors get canonical-import for free.

**A new sample estate:** add an `IndustryProfile` (domains, sensitive domains, table naming, agent and
KPI names) or a `MaturityProfile` (coverage dials) to `connectors/profiles.py`, then list the
organisation in `seed/bootstrap.py`. Profiles set estate facts only — a profile cannot set a grade.

**A new playbook:** add an entry to `playbooks.yaml` naming the check it fixes, its target, horizon and
effort. The engine simulates its impact automatically.
