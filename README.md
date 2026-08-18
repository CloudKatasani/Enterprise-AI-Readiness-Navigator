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

Run the tests with `cd backend && .venv/bin/pip install -r requirements-dev.txt` then
`.venv/bin/python -m pytest` — `requirements.txt` alone carries no test runner.

[RUNNING.md](RUNNING.md) covers the same ground in more detail: configuration, custom ports,
production mode, resetting the database, and what to do when a page says the API is unreachable.

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

### Live Demo — assess an estate shaped like yours

`/demo` is the tab to open in front of a customer. They choose, in order:

- **industry first** — which then filters the **organization** picker to the estates that industry
  actually has on the Organizations tab, each shown with its current score and grade. Picking one
  prefills the **size band** it is assessed at, which they can change to see the other peer cohort;
  or they pick *Another organization* and type a name. Running as an existing organization creates a
  separate `demo-` tenant named `<name> (demo run)` — the reference assessment is never overwritten;
- **enterprise data platform** — Snowflake, Databricks, Microsoft Fabric, BigQuery, Redshift, Oracle
  Exadata or Teradata;
- **data governance tool** — Collibra, Alation, Informatica CDGC, Atlan, Purview, or platform-native
  only;
- **data quality tooling** — Monte Carlo, Great Expectations, Soda, Ataccama, Snowflake-native,
  Oracle EDQ, or platform-native only;
- **governance maturity**, plus a seed;
- **assessment scope** — leave the agent estate, retrieval corpora, ML assets or semantic layer out
  and those checks are reported as *not measured*, exactly as a real estate without that surface
  produces. They are never scored as zero.

**Run evaluation now** generates the estate to that shape and puts it through the same pipeline a
real harvest goes through — harvest → evaluate → score → cap → benchmark → recommend → freeze — in
about a second, then lands on the executive view for the organisation it just created. The snapshot
is a real snapshot: `/verify` replays it, and the same configuration and seed reproduce it exactly.

Every estate then carries a fourth tab, **Action plan** (`/estates/{snapshot_id}/actions`):

- **hard blockers first**, with the objects that fail them and the play that clears each;
- **architect items** — every criterion below its rubric target, ranked by pillar weight × criterion
  weight × distance from target, plus any coverage gaps the connectors could not observe;
- **steward items** — the evidence held below the confidence threshold awaiting a decision, and the
  findings queue with the failing objects;
- **sequenced guidance** — the roadmap with the projected composite and grade after each horizon,
  measured by re-scoring rather than estimated.

### Scoring Pillars — the academy page

`/pillars` is the reference for someone new to AI adoption. For each of the eight pillars and both
overlay indices it sets out:

- **why the pillar exists** and what changes once machines rather than people consume the data;
- **what goes wrong without it** — concrete failure modes, not abstractions;
- **what good looks like**;
- **what you give up by leaving the pillar out of an assessment**, which is a different question
  from having a weak estate: omit Security and an estate with unprotected classified columns can
  reach AI-Ready, because the cap that would have held it at 49 no longer exists;
- **the checks that actually measure it**, with their weights and targets;
- **references** — the standards, frameworks and papers behind the argument (NIST AI RMF, EU AI Act
  Art. 10, ISO/IEC 25012 and 42001, OWASP LLM Top 10, MITRE ATLAS, DAMA-DMBOK, and the RAG,
  text-to-SQL and ML-debt literature).

Each pillar also shows how the assessed organisations on this instance actually spread on it, so the
argument sits next to real numbers — and where the median lands exactly on a cap value, the page
says so.

The explanatory content lives in [`pillar_guide_v1.yaml`](backend/eairn/seed/pillar_guide_v1.yaml),
versioned alongside the rubric it explains. Weights, questions, targets and checks are read from the
rubric tables and never restated in the guide, so the two cannot disagree; tests assert that every
rubric pillar and index has teaching content and that every number on the page comes from the rubric.

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

### API Documentation — the wiring diagram for a real deployment

`/api-docs` is the page for whoever has to turn the demo into a running system. For every connector
in the registry it publishes, on one card:

- **what to configure** — each connection key, whether it is required, whether it is a secret, and a
  worked example. Secret values are placeholders or the mount path they are read from; a test asserts
  that no real credential can reach the table;
- **which credential to mint** — the supported auth modes with the recommended one marked (key-pair
  for Snowflake, OAuth M2M for Databricks, an Entra application for Fabric and Purview, workload
  identity federation for BigQuery), alongside the least-privilege grant from the permission manifest;
- **which hosts the runtime must reach** — every egress hostname and port, so the allowlist for a
  deployment is the union of the connectors it enables and nothing else;
- **every statement and endpoint it may issue**, verbatim. The catalog is complete: a connector
  cannot call anything absent from it;
- **what connecting it unlocks**, counted in checks and grouped by pillar — and what stays *not
  measured* until another source covers it;
- **freshness, paging and rate limits**, each pointing at the vendor document that is authoritative.

Two things on the page are computed rather than claimed. Every catalogued call is re-run through the
same read-only guard the executor uses *as the page renders*, and the violation count is published in
the header — a mutating statement could not be documented here for the same reason it could not be
executed. And the check coverage is derived from the check library's own capability requirements, so
it moves when a check does.

Above the connectors sits what a hosted deployment needs regardless of platform: what runs, where
secrets live on each hyperscaler, the backend environment variables with this instance's current
values beside them, and the five-step sequence from provisioning a principal to verifying that a
snapshot replays. Below them, the **capability matrix** answers the question a coverage gap actually
raises — *which platform do I have to connect before RG-005 stops reporting as not measured?*

Operational detail lives in [`integration_v1.yaml`](backend/eairn/seed/integration_v1.yaml); the
contract — capabilities, grants, statement and endpoint catalogs — is read from the connector
registry at request time, so the page cannot document a call the code does not make. A test asserts
that every registered connector has a guide entry, so a new connector cannot appear with an empty
configuration section that reads as *needs nothing*.

### Data Model — the database underneath

`/data-model` is the page for whoever has to point this at Postgres on AWS, Azure or GCP. Every
table, column, type, key, index and foreign key is introspected from the ORM as the page renders, so
the schema and its documentation are the same artefact — a migration that adds a column adds it here.

The thirty-one tables are grouped into four families, because which family a table belongs to is what
explains its lifecycle: **tenancy and harvest** (mutable configuration), the **canonical metadata
model** (replaced on each harvest), **rubric as data** (versioned, and immutable once a snapshot
cites it), and **evidence, scores and snapshots** (append-only). Each canonical table carries the
connector capability that populates it, which is the API Documentation view's coverage story read
from the other direction.

Each table expands to its full column list — generic type, the type Postgres will actually create,
nullability and key role — plus the live row count on this instance and the **Postgres DDL** the
deployment gets. The per-column Postgres type comes from the same DDL compiler as the `CREATE TABLE`
below it, so the two cannot disagree about an identity column rendering as `SERIAL`.

The deployment section names the managed Postgres service and connection string for each hyperscaler,
flags when the running instance is on SQLite rather than a production target, and states the four
things a reviewer asks: SQLite is development-only, real deployments run Alembic rather than
`create_all`, no customer rows are stored under any configuration, and every tenant-keyed table
cascades back to `tenants` so removing an organisation is one statement rather than a cleanup script.

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
| `GET /api/demo/options` | Platforms, governance and DQ tooling, scopes and profiles a live demo may choose |
| `POST /api/demo/run` | Generate a synthetic estate to that shape and assess it end to end |
| `GET /api/assessments/{id}/action-plan` | Blockers, architect items, steward items and sequenced guidance for one snapshot |
| `GET /api/pillars` | The scoring-pillar guide: rubric structure, teaching content, references and the live portfolio spread per pillar |
| `GET /api/integration` | Deployment and connector wiring: auth modes, configuration keys, egress hosts, the verbatim statement/endpoint catalog re-validated as read-only, and the checks each connector unlocks |
| `GET /api/data-model` | Every table introspected from the ORM: columns, keys, indexes, Postgres DDL, live row counts and the hyperscaler deployment targets |
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
