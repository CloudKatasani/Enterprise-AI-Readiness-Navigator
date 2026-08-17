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
.venv/bin/python -m eairn.seed.bootstrap          # 13 demo estates across 6 industries
.venv/bin/uvicorn eairn.main:app --port 8000      # OpenAPI docs at /docs

# 2. Portal — role-scoped views over the snapshot
cd ../frontend
npm install
npm run dev                                       # http://localhost:3000
```

The bootstrap seeds a portfolio of sample estates — six industries, four maturity profiles, each
scored from its own evidence:

```
Organisation                 Industry               Composite  Grade           ARI   RRI
----------------------------------------------------------------------------------------
Northwind Financial          financial_services          58.5  AI-Emerging    39.0  39.0
Calder & Voss Capital        financial_services          84.3  AI-Ready       95.2  94.4
Basalt Mutual                financial_services          36.2  AI-At-Risk     16.8  28.3
Meridian Telecom             telecommunications          74.6  AI-Capable     79.5  84.2
Harborline Retail Group      retail                      60.0  AI-Capable     39.0  39.0
Anvil Grid Utilities         utilities                   32.9  AI-At-Risk     15.0  28.3
Loftware Technologies        technology                  84.8  AI-Ready       95.0  94.4
Silverpine Health System     healthcare                  73.9  AI-Capable     79.5  84.2
...
```

Seed one estate on its own with `--only <key>` (for example `--only anvil-grid`).

Run the tests with `cd backend && .venv/bin/python -m pytest`.

---

## What it does

### Sample estates across six industries

The demo connector generates deterministic estates along two independent axes. **Industry**
(financial services, telecommunications, retail, utilities, technology, healthcare) decides the
business domains, the dominant platform and where regulated data concentrates — a utility's crown
jewels sit in metering and outage data, a telco's in subscriber and roaming records. **Maturity**
(leading, advancing, emerging, at-risk) decides the coverage a governance programme has actually
achieved. Neither sets a score: they set estate facts, and the check library measures whatever those
facts support.

### Eight scored pillars, plus two overlay indices

Data Quality (20%) · Governance (20%) · Metadata (15%) · Security (15%) · Semantic Layer (10%) ·
AI Engineering (10%) · Agent Readiness (10%), plus the **Agent Readiness Index** and **RAG Readiness
Index** scored as separate overlays so an agent or RAG programme can be funded on its own evidence.
(`ARI` and `RRI` remain the machine-readable keys; the Portal always shows the full names.)

Fifty-three automated checks produce the evidence. Each declares the connector capabilities it needs;
a check whose evidence source is unavailable is reported as **not measured**, never scored as zero.

### Hard blockers that actually bind

Some findings cap a score regardless of arithmetic, and the caps are rubric data rather than code:

- classified columns with no masking, redaction or policy tag → **Security capped at 49**
- agent actions that are not attributable and replayable → **Agent Readiness capped at 39**
- classified content in a vector index with no retrieval-time filtering → **RAG Readiness Index
  capped at 39**

The executive view leads with these, because clearing them is the shortest path to a better grade.
A blocker is reported whenever its condition fires, including when the estate already scores below
the cap and there is nothing left to lower — "no cap applied" is not "no blocker", and hiding it
would flatter the weakest estates.

### A roadmap ordered by simulation, not opinion

Playbooks are data ([`playbooks.yaml`](backend/eairn/seed/playbooks.yaml)). For each triggered play
the Recommendation Engine re-runs the scoring engine with that play's target applied and reports the
**measured** composite delta and any hard-blocker cap the play would clear — then ranks by impact per
effort day. `POST /api/assessments/{id}/simulate` exposes the same what-if to any caller.

### A page per organisation, three role-scoped views within it

`/` — **Organizations** in the masthead — is the portfolio: every assessed organisation grouped by
industry, each card showing composite, grade, Agent Readiness Index, RAG Readiness Index and blocker
count. Each card is a link to that organisation's own page at `/estates/{snapshot_id}` —
bookmarkable, shareable, and openable in a new tab, because a readiness result belongs to one
organisation and one immutable snapshot. Inside it, three role views sit behind tabs that always
carry the snapshot in the path:

- **Executive** (`/estates/{snapshot_id}`) — grade and trend, peer percentile with the cohort
  definition alongside it, hard blockers, top-5 risks, and the roadmap with investment vs projected
  score.
- **Architect** (`/estates/{snapshot_id}/architect`) — pillar heatmap by platform and business domain,
  with drill-through from any score to the evidence records behind it.
- **Steward** (`/estates/{snapshot_id}/steward`) — the low-confidence review queue, the findings queue
  with the exact failing objects, and draft recommendations awaiting approval.

The masthead's Architect and Steward entries list the organisations for that role rather than
defaulting to one: no view ever shows an estate the reader did not choose.

### A methodology page that shows its working

`/methodology` is the page to hand a client who asks *"where does this number come from?"*. It works
the entire calculation through one estate's own evidence:

1. **The sample data** — the harvest the score was computed from, down to sample datasets, columns,
   policies, grants, agents and corpora. For the demo portfolio it states plainly that the estate is
   synthetic, names the industry and maturity profiles that shaped it and the seed that reproduces
   it, and says what changes in a real assessment (the connector, and nothing else).
2. **One check → one evidence record** — a single check narrated field by field: what was counted,
   the division that produced the result, the confidence tier, and the objects that failed.
3. **Criteria → pillar score** — every pillar's full criterion table with `score × weight`, the
   weighted mean, and the cap if one binds.
4. **Pillars → composite** — the same arithmetic one level up, with the grade band it lands in.
5. **Hard blockers**, **the two overlay indices**, and **the confidence tiers** that decide what is
   allowed to count at all.
6. **What is missing** — the criteria that produced no score, kept apart by *kind*: the connector
   could not observe it, the evidence is waiting on a reviewer, or the estate contains nothing of
   that kind. Plus what EAIRN never collects under any configuration.

Every weighted mean on that page is **recomputed in the view** from the stored score lines and
compared with what the Scoring Engine wrote; each one is labelled with whether it reconciles, and a
test asserts that all of them do.

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
| `GET /api/portfolio` | Assessed organisations grouped by industry, latest snapshot each |
| `GET /api/methodology?snapshot=` | The full calculation worked through one snapshot: harvest provenance, per-pillar arithmetic recomputed and reconciled against the engine, caps, indices, confidence tiers and every coverage gap |
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
