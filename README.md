# Enterprise AI Readiness Navigator (EAIRN)

EAIRN is a vendor-neutral assessment and advisory platform that answers a question every enterprise
is now asking: **"Is our data platform actually ready for GenAI, agentic AI, and RAG — and if not,
what exactly do we fix first?"**

It connects read-only to the metadata, governance, lineage, catalog, quality and security layers of a
data estate, computes a weighted, evidence-backed readiness score across eight pillars, benchmarks
the result against anonymised peers, and produces a prioritised, costed remediation roadmap.

This repository implements the product described in
[`EAIRN_Blueprint_Detailed.docx`](EAIRN_Blueprint_Detailed.docx). See
[docs/implementation-status.md](docs/implementation-status.md) for a section-by-section map of what
is built and what is on the roadmap.

---

## Five design principles, enforced in code

| Principle | How it is enforced |
|---|---|
| **Evidence over opinion** | Every score derives from `{check_id, target, result, confidence, rationale}` evidence records. Questionnaire answers are supplementary, recorded at self-reported confidence, and cross-validated against the measurement (check `GV-009`). |
| **Metadata-only by default** | No connector requests row-data access; CI asserts it (`tests/test_connector_kill_test.py`). Row sampling is a separate, permission-gated module and every authorisation is logged per dataset. |
| **Rubrics as data** | Pillars, criteria, weights, grade bands and hard-blocker overrides live in [`rubric_v2.0.yaml`](backend/eairn/seed/rubric_v2.0.yaml) and are loaded into versioned tables. The scoring engine contains no readiness opinion of its own. |
| **Explainable inferences** | Every record carries a confidence tier. Anything below the rubric threshold (default 0.80) is queued for human review and excluded from scoring until a reviewer decides. |
| **Reproducible snapshots** | Each run is frozen under `{tenant, snapshot_id, rubric_version, harvested_at}` with a hash over rubric version + evidence + scores. `GET /api/assessments/{id}/verify` replays the engine and proves the hash still matches. |

---

## Quickstart

```bash
# 1. Backend — API, scoring engine, connectors
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m eairn.seed.bootstrap          # deterministic demo estate + one snapshot
.venv/bin/uvicorn eairn.main:app --port 8000      # OpenAPI docs at /docs

# 2. Portal — role-scoped views over the snapshot
cd ../frontend
npm install
npm run dev                                       # http://localhost:3000
```

The bootstrap prints the snapshot it produced:

```
tenant           : Northwind Financial (northwind)
snapshot         : snap_cccc9c8c6ff900e2
composite        : 59.5 (AI-Emerging)
ARI              : 57.6 (Agent-Emerging)
RRI              : 39.0 (RAG-At-Risk)
caps applied     : ['no_agent_action_audit', 'unprotected_classified_columns', 'rag_acl_not_enforced']
snapshot hash    : 5ec29962936d3ede...
```

Run the tests with `cd backend && .venv/bin/python -m pytest`.

---

## What it does

### Eight scored pillars, plus two overlay indices

Data Quality (20%) · Governance (20%) · Metadata (15%) · Security (15%) · Semantic Layer (10%) ·
AI Engineering (10%) · Agent Readiness (10%), plus the **Agent Readiness Index (ARI)** and **RAG
Readiness Index (RRI)** scored as separate overlays so an agent or RAG programme can be funded on its
own evidence.

Forty-six automated checks produce the evidence. Each declares the connector capabilities it needs;
a check whose evidence source is unavailable is reported as **not measured**, never scored as zero.

### Hard blockers that actually bind

Some findings cap a score regardless of arithmetic, and the caps are rubric data rather than code:

- classified columns with no masking, redaction or policy tag → **Security capped at 49**
- agent actions that are not attributable and replayable → **Agent Readiness capped at 39**
- classified content in a vector index with no retrieval-time filtering → **RRI capped at 39**

The executive view leads with these, because clearing them is the shortest path to a better grade.

### A roadmap ordered by simulation, not opinion

Playbooks are data ([`playbooks.yaml`](backend/eairn/seed/playbooks.yaml)). For each triggered play
the Recommendation Engine re-runs the scoring engine with that play's target applied and reports the
**measured** composite delta and any hard-blocker cap the play would clear — then ranks by impact per
effort day. `POST /api/assessments/{id}/simulate` exposes the same what-if to any caller.

### Three role-scoped views

- **Executive** — composite and grade, trend, peer percentile with the cohort definition alongside it,
  hard blockers, top-5 risks, and the roadmap with investment vs projected score.
- **Architect** — pillar heatmap by platform and business domain, with drill-through from any score to
  the evidence records behind it.
- **Steward** — the low-confidence review queue, the findings queue with the exact failing objects, and
  draft recommendations awaiting approval.

---

## Architecture

```
Portal (Next.js)  ──►  API (FastAPI)
                          │
        ┌─────────────────┼──────────────────┬──────────────┬─────────────────┐
        ▼                 ▼                  ▼              ▼                 ▼
   Connectors       Metadata Engine    Scoring Engine   Recommendation    AI Advisor
   (read-only)      (canonical model)  (rubric as data)    Engine       (grounded in
        │                 │                  │          (playbooks as     the snapshot)
        └───► harvest ───►│                  │            data)
                          ▼                  ▼
                     Evidence records ──► Immutable snapshot (hash-keyed)
```

Details in [docs/architecture.md](docs/architecture.md).

### Connector status

| Connector | Live harvest | Notes |
|---|---|---|
| Snowflake | ✅ | Reference implementation. ACCOUNT_USAGE / INFORMATION_SCHEMA only, via `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`. |
| Demo | ✅ | Deterministic synthetic estate used for demos and golden tests. |
| Databricks, Fabric | Bundle | Permission manifest and system-table/API catalog published; live driver in roadmap phase P2. |
| BigQuery | Bundle | P3. |
| Oracle Exadata | Bundle | P4. |
| Collibra, Alation, Purview, Atlan, Informatica | Bundle | Governance tools — harvested as evidence *and* scored as subjects. |
| Monte Carlo, Great Expectations, Soda, Ataccama | Bundle | DQ tools — coverage, effectiveness and response, not tool presence. |

"Bundle" connectors can assess an estate **today** from a canonical metadata export
(`bundle=<path>`), which is also how a delivery partner runs an assessment without provisioning a
service principal.

---

## API

`GET /docs` serves the full OpenAPI UI. The endpoints the Portal uses:

| Endpoint | Purpose |
|---|---|
| `GET /api/connectors` | Connector catalog with the permission manifest published to the customer |
| `GET /api/checks`, `GET /api/rubrics/{version}`, `GET /api/playbooks` | The rubric, check library and playbook library as data |
| `POST /api/assessments` | Run harvest → evaluate → score → recommend → snapshot |
| `GET /api/assessments/{id}/dashboard/{executive\|architect\|steward}` | Role-scoped views |
| `GET /api/assessments/{id}/evidence`, `GET /api/evidence/{id}` | Evidence drill-through |
| `POST /api/evidence/{id}/review` | Accept/reject a low-confidence finding, then re-score |
| `POST /api/assessments/{id}/simulate` | What-if against named checks |
| `GET /api/assessments/{id}/verify` | Replay the snapshot and compare hashes |
| `POST /api/assessments/{id}/advisor` | Draft an executive narrative grounded in the snapshot |
| `POST /api/sampling-authorizations` | Log an explicit, per-dataset row-sampling authorisation |

---

## Configuration

Backend settings use the `EAIRN_` prefix (see [`config.py`](backend/eairn/config.py)):

| Variable | Default | Meaning |
|---|---|---|
| `EAIRN_DATABASE_URL` | SQLite file | Postgres is the production target; SQLite keeps dev and CI dependency-free |
| `EAIRN_DEFAULT_RUBRIC_VERSION` | `2.0` | Rubric new assessments score against |
| `EAIRN_CONFIDENCE_THRESHOLD` | `0.80` | Below this, evidence queues for review instead of scoring |
| `EAIRN_ALLOW_ROW_SAMPLING` | `false` | The default build has no row-data path at all |
| `EAIRN_ANTHROPIC_API_KEY` | unset | Without it the AI Advisor uses deterministic, evidence-grounded templates |
| `EAIRN_ADVISOR_MODEL` | `claude-opus-5` | Advisor model |

Frontend: `EAIRN_API_URL` (default `http://127.0.0.1:8000`).

---

## Engineering constraints (non-negotiable)

1. **Least privilege, published.** Every connector ships a permission manifest naming the exact grants
   it needs and the exact statements it may issue. Both are rendered in the Portal.
2. **The kill test.** CI asserts that every catalogued statement is non-mutating, that every API entry
   uses a read-only method, that the guard rejects the mutations it exists to reject, and that no
   connector declares row-data access.
3. **No row-data path by default.** Sampling is a separate package; authorisations are logged per
   dataset with justification and expiry.
4. **Every LLM-generated artefact stores its prompt, evidence citations, confidence and reviewer
   decision**, and lands in `draft` status. Humans approve; EAIRN does not auto-remediate.
