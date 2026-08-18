# Running EAIRN locally

Everything in this guide was run end to end from a clean checkout on the versions listed below. No
cloud account, no platform credential and no API key is needed: the demo connector generates its
estates in-process, and the AI Advisor falls back to deterministic templates when no key is present.

---

## What you are starting

Two processes and one file:

| Piece | Command | Default | What it is |
|---|---|---|---|
| **API** | `uvicorn eairn.main:app` | `http://127.0.0.1:8000` | FastAPI: connectors, check library, scoring engine, recommendation engine. OpenAPI docs at `/docs`. |
| **Portal** | `npm run dev` | `http://localhost:3000` | Next.js. Every page is server-rendered and calls the API server-side. |
| **Database** | — | `backend/eairn.db` | SQLite, created on first start. Gitignored, and safe to delete. |

The Portal never calls the API from the browser — pages are server components and the Live Demo runs
through a server action — so the two processes talk to each other over loopback and nothing about
this setup needs CORS.

## Prerequisites

- **Python 3.11 or newer.** Tested on 3.11.
- **Node 20.9 or newer.** Next.js 16 requires it; tested on Node 22.
- Roughly 500 MB of disk for `node_modules` and the Python virtualenv.

---

## First run

Two terminals. Terminal one, the API:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m eairn.seed.bootstrap        # 13 demo estates across 6 industries
.venv/bin/uvicorn eairn.main:app --port 8000
```

The bootstrap takes a minute or so and prints each organisation as it scores. It is a one-time step
for a fresh database — the API creates its schema, installs rubric 2.0 and loads the peer cohorts on
startup, but it does not invent estates for you, so without this step the Portal comes up correctly
and reports that there is nothing to show.

Terminal two, the Portal:

```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:3000**.

### Where to look first

| Page | What it is |
|---|---|
| `/` | The portfolio — 13 assessed organisations grouped by industry. Each card opens that organisation's own page. |
| `/estates/{snapshot_id}` | One organisation: executive, architect, steward and action-plan views. |
| `/demo` | Assess a synthetic estate shaped like the customer's, end to end, in front of them. |
| `/methodology` | The whole calculation worked through one estate's own evidence. |
| `/api-docs` | How to wire this to real platforms — auth, config keys, egress hosts, every call. |
| `/data-model` | The database underneath, introspected live, with the Postgres DDL. |
| `http://127.0.0.1:8000/docs` | Interactive OpenAPI browser for the API. |

---

## Seeding

```bash
.venv/bin/python -m eairn.seed.bootstrap                      # the whole portfolio
.venv/bin/python -m eairn.seed.bootstrap --only anvil-grid    # one organisation
.venv/bin/python -m eairn.seed.bootstrap --label "Q3 rerun"   # label the snapshot
```

Organisation keys: `northwind`, `calder-voss`, `basalt-mutual`, `meridian-telecom`,
`northbeam-wireless`, `harborline-retail`, `tessella-markets`, `anvil-grid`, `cascadia-power`,
`loftware`, `quanta-cloud`, `silverpine-health`, `arbor-clinical`.

Re-running is idempotent per organisation: it replaces that tenant's canonical data and appends a
**new** snapshot rather than overwriting the old one. That is also how the executive view's trend
line gets its second point — run the bootstrap twice to see it.

To start over completely, stop the API and delete the database:

```bash
rm backend/eairn.db
```

---

## Tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt   # adds pytest; requirements.txt alone has no test runner
.venv/bin/python -m pytest
```

76 tests, a few seconds. They default to a throwaway SQLite file in a temp directory, so they
normally neither read nor disturb `backend/eairn.db`. One caveat: the default is applied with
`setdefault`, so an `EAIRN_DATABASE_URL` already exported in your shell wins and the tests will write
to *that* database. Unset it before running them if you have pointed it somewhere you care about.

The frontend has no test suite; `npx tsc --noEmit` type-checks it.

---

## Configuration

Backend settings are read from the environment with the `EAIRN_` prefix, or from `backend/.env`
(gitignored). Every one has a working default — this table is what you would change, not what you
must set.

| Variable | Default | Effect |
|---|---|---|
| `EAIRN_DATABASE_URL` | `sqlite:///backend/eairn.db` | Point at Postgres for anything beyond local development. |
| `EAIRN_DEFAULT_RUBRIC_VERSION` | `2.0` | Rubric new assessments run against. |
| `EAIRN_CONFIDENCE_THRESHOLD` | `0.80` | Findings below this queue for review instead of scoring. |
| `EAIRN_ALLOW_ROW_SAMPLING` | `false` | Even when true, per-dataset authorization records are still required. |
| `EAIRN_ANTHROPIC_API_KEY` | unset | With a key the AI Advisor drafts narratives; without one it uses evidence-grounded templates. Everything else is unaffected. |
| `EAIRN_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Only matters if something calls the API from a browser. The Portal does not. |

The Portal reads one variable:

| Variable | Default | Effect |
|---|---|---|
| `EAIRN_API_URL` | `http://127.0.0.1:8000` | Where the server-side API client points. |

`GET /health` reports the rubric version, confidence threshold, row-sampling flag and whether the
advisor found a key. For the rest, `/api-docs` shows this instance's current value beside each
documented default — the quickest way to confirm a setting actually took effect.

### Different ports

```bash
# API
.venv/bin/uvicorn eairn.main:app --port 8001

# Portal — EAIRN_API_URL has to match, or the Portal renders the "API not reachable" notice
EAIRN_API_URL=http://127.0.0.1:8001 npm run dev -- -p 3001
```

### Production mode locally

```bash
cd frontend
npm run build
npm start
```

Every page is `force-dynamic` — a readiness score read from a cache is a wrong readiness score — so
the build compiles the app but renders nothing ahead of time, and the API still has to be running.

---

## Troubleshooting

**"The EAIRN API is not reachable"** — the Portal is up and the API is not. Every page renders this
notice with the exact URL it tried, rather than failing, because it is the most likely first-run
state. Check terminal one, and check `EAIRN_API_URL` if you changed ports.

**"No assessments yet"** — the API is up but the database is empty. Run the bootstrap.

**`Another next dev server is already running`** — Next.js 16 allows one dev server per directory
and prints the PID of the existing one. `kill <pid>` and start again. This survives a crashed
terminal, so it can appear when nothing is actually listening.

**`Address already in use`** — something else holds 8000 or 3000. Use different ports as above.

**`No module named pytest`** — you installed `requirements.txt` but not `requirements-dev.txt`.

**`no such table: rubrics`** — a database file that predates a schema change. Delete
`backend/eairn.db` and re-seed; nothing in it is precious. (The API creates its schema on startup,
so this only appears if you point at a database created by an older checkout.)

**Bootstrap seems to hang** — it scores 13 estates through the full pipeline. Give it a minute; it
prints each organisation as it completes.

---

## What this does *not* do locally

- **No outbound network calls.** The seeded portfolio is generated by the demo connector. Nothing
  contacts Snowflake, Databricks, Fabric, BigQuery, Oracle or any governance tool unless you
  configure a connection yourself — see `/api-docs` for what that takes.
- **No row data, ever.** Not from the demo estates, and not from a real platform: connectors read
  catalog metadata only, and CI asserts that every catalogued statement is non-mutating.
- **SQLite is development-only.** The schema relies on foreign-key cascades and concurrent writers
  that Postgres handles properly. `/data-model` shows the Postgres DDL a real deployment gets, and
  flags when the running instance is on SQLite.
