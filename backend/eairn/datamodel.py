"""Data Model view: the database EAIRN actually creates, read from the ORM.

Nothing on this page is transcribed. Tables, columns, types, keys, indexes and
the Postgres DDL are all introspected from ``Base.metadata`` at request time, so
the documentation and the schema are the same artefact -- a migration that adds a
column adds it here, and a page that disagreed with the database would be a
contradiction the code cannot express.

Three things are layered on top of the introspection, because a bare schema dump
does not answer the questions a reader arrives with:

* **Families.** The schema divides into tenancy, the canonical metadata model,
  rubric-as-data, and the immutable assessment record. Which family a table
  belongs to explains its lifecycle -- harvested and replaced, versioned and
  installed, or written once and never updated.
* **Provenance.** Canonical tables are annotated with the connector capability
  that populates them, so a reader can trace a column back to the platform call
  that produced it.
* **Postgres DDL.** SQLite is the dev default; Postgres is the production
  target. The DDL rendered here is what a Postgres deployment gets, including
  the SERIAL and type mappings that differ from SQLite.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable, Table

from eairn.checks import REGISTRY as CHECK_REGISTRY
from eairn.config import Settings
from eairn.models import Base

_PG = postgresql.dialect()
#: The same DDL compiler CreateTable uses, so the per-column Postgres type on the
#: page and the type in the rendered DDL are produced by one code path. Compiling
#: the type alone would say INTEGER where Postgres actually creates a SERIAL.
_PG_DDL = _PG.ddl_compiler(_PG, None)

#: Table -> family. Ordering within a family is declaration order in models.py,
#: which is already read-order: a table is defined after the thing it references.
FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "key": "tenancy",
        "name": "Tenancy and harvest",
        "lifecycle": "Mutable configuration and run history.",
        "summary": (
            "One row per assessed organisation, the read-only connections configured "
            "against it, and the history of harvest runs. Connection configuration is "
            "non-secret by construction — credentials live in the platform's secret "
            "store, never in this table."
        ),
        "tables": ("tenants", "connections", "harvest_runs"),
    },
    {
        "key": "canonical",
        "name": "Canonical metadata model",
        "lifecycle": "Replaced on each harvest; the current picture of the estate.",
        "summary": (
            "The platform-neutral shape every connector normalises into. No row data "
            "ever lands here: these tables hold catalog-level metadata — inventories, "
            "classifications, policy attachments, lineage edges, grant graphs, "
            "aggregated usage counts — plus the AI, agent and retrieval surfaces the "
            "readiness indices need. This is the family a new connector has to "
            "populate, and the reason a connector for a new platform needs no change "
            "to the scoring engine."
        ),
        "tables": (
            "datasets",
            "columns",
            "lineage_edges",
            "policies",
            "grants",
            "usage_events",
            "dq_monitors",
            "dq_incidents",
            "ml_assets",
            "semantic_models",
            "kpi_definitions",
            "agent_assets",
            "rag_corpora",
            "governance_programs",
            "questionnaire_responses",
            "sampling_authorizations",
        ),
    },
    {
        "key": "rubric",
        "name": "Rubric as data",
        "lifecycle": "Versioned and installed; immutable once a snapshot cites it.",
        "summary": (
            "Pillars, criteria, weights, grade bands, hard-blocker overrides and index "
            "dimensions — all versioned rows rather than constants in the engine. "
            "Scoring reads these tables, so a fork can reweight the rubric, rename an "
            "index or add a criterion without touching code, and every snapshot records "
            "the rubric version it was scored against."
        ),
        "tables": (
            "rubrics",
            "rubric_pillars",
            "rubric_criteria",
            "rubric_grade_bands",
            "rubric_overrides",
            "rubric_index_dimensions",
        ),
    },
    {
        "key": "assessment",
        "name": "Evidence, scores and snapshots",
        "lifecycle": "Append-only. A frozen snapshot is never updated in place.",
        "summary": (
            "The immutable record: one assessment per run, the evidence records behind "
            "every number, the score tree derived from them, the remediation plan and "
            "the advisor narrative that cites them. Evidence carries its own confidence "
            "and review state, which is what lets a low-confidence finding queue for a "
            "human instead of quietly moving a score."
        ),
        "tables": (
            "assessments",
            "evidence",
            "scores",
            "recommendations",
            "advisor_narratives",
            "cohort_stats",
        ),
    },
)

#: Canonical table -> the connector capability that populates it. This is the
#: API Documentation view's coverage story read from the other direction: it says
#: which platform call has to succeed before a table has rows at all.
POPULATED_BY: dict[str, str] = {
    "datasets": "datasets",
    "columns": "columns",
    "lineage_edges": "lineage",
    "policies": "policies",
    "grants": "grants",
    "usage_events": "usage",
    "dq_monitors": "dq_monitors",
    "dq_incidents": "dq_incidents",
    "ml_assets": "ml_assets",
    "semantic_models": "semantic_models",
    "kpi_definitions": "kpi_definitions",
    "agent_assets": "agents",
    "rag_corpora": "rag_corpora",
    "governance_programs": "governance_program",
}


def _orm_classes() -> dict[str, Any]:
    return {
        mapper.class_.__tablename__: mapper.class_
        for mapper in Base.registry.mappers
        if hasattr(mapper.class_, "__tablename__")
    }


def _purpose(cls: Any) -> str:
    """The ORM class docstring, which is where a table's intent is already written."""
    doc = (cls.__doc__ or "").strip()
    return " ".join(line.strip() for line in doc.splitlines() if line.strip())


def _postgres_column_type(column: Any) -> str:
    """The column's type as Postgres will create it, taken from the DDL compiler."""
    spec = _PG_DDL.get_column_specification(column)
    # "<name> <type...> [NOT NULL]" -- drop the name and the nullability, both of
    # which the table already shows in their own columns.
    without_name = spec[len(column.name) :].strip()
    return without_name.removesuffix("NOT NULL").strip() or without_name


def _column(table: Table, column: Any) -> dict[str, Any]:
    indexed = any(
        len(index.columns) == 1 and column.name in index.columns for index in table.indexes
    )
    unique = any(
        column.name in constraint.columns
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )
    return {
        "name": column.name,
        "type": str(column.type),
        "postgres_type": _postgres_column_type(column),
        "nullable": bool(column.nullable),
        "primary_key": bool(column.primary_key),
        "foreign_keys": sorted(fk.target_fullname for fk in column.foreign_keys),
        "indexed": indexed,
        "unique": unique,
        "has_default": column.default is not None or column.server_default is not None,
    }


def _row_count(session: Session | None, table: Table) -> int | None:
    """Live row count, or None when the table has not been created yet.

    A first-run deployment reaches this page before init_db, and a missing
    table is a legitimate state to render rather than a 500.
    """
    if session is None:
        return None
    try:
        return int(session.scalar(select(func.count()).select_from(table)) or 0)
    except SQLAlchemyError:
        session.rollback()
        return None


def _postgres_ddl(table: Table) -> str:
    statements = [str(CreateTable(table).compile(dialect=_PG)).strip().rstrip(";") + ";"]
    statements += [
        str(CreateIndex(index).compile(dialect=_PG)).strip().rstrip(";") + ";"
        for index in sorted(table.indexes, key=lambda i: i.name or "")
    ]
    return "\n".join(statements)


def _table_entry(table: Table, cls: Any, session: Session | None) -> dict[str, Any]:
    return {
        "name": table.name,
        "class_name": cls.__name__ if cls is not None else "",
        "purpose": _purpose(cls) if cls is not None else "",
        "populated_by_capability": POPULATED_BY.get(table.name),
        "columns": [_column(table, column) for column in table.columns],
        "primary_key": [c.name for c in table.primary_key.columns],
        "foreign_keys": sorted(
            {
                (fk.parent.name, fk.target_fullname, constraint.ondelete or "")
                for constraint in table.foreign_key_constraints
                for fk in constraint.elements
            }
        ),
        "unique_constraints": [
            {"name": constraint.name, "columns": [c.name for c in constraint.columns]}
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ],
        "indexes": [
            {"name": index.name, "columns": [c.name for c in index.columns], "unique": bool(index.unique)}
            for index in sorted(table.indexes, key=lambda i: i.name or "")
        ],
        "postgres_ddl": _postgres_ddl(table),
        "row_count": _row_count(session, table),
    }


def _relationships() -> list[dict[str, str]]:
    """Foreign-key edges across the whole schema, for reading the shape at a glance."""
    edges = []
    for table in Base.metadata.sorted_tables:
        for constraint in table.foreign_key_constraints:
            for fk in constraint.elements:
                target_table, _, target_column = fk.target_fullname.partition(".")
                edges.append(
                    {
                        "from_table": table.name,
                        "from_column": fk.parent.name,
                        "to_table": target_table,
                        "to_column": target_column,
                        "on_delete": constraint.ondelete or "",
                    }
                )
    return sorted(edges, key=lambda e: (e["from_table"], e["from_column"]))


def data_model_view(session: Session | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """The Data Model view: every table, its Postgres DDL, and what fills it."""
    classes = _orm_classes()
    tables = {table.name: table for table in Base.metadata.sorted_tables}
    placed: set[str] = set()

    families = []
    for family in FAMILIES:
        entries = []
        for name in family["tables"]:
            table = tables.get(name)
            if table is None:  # pragma: no cover - a renamed table with a stale family map
                continue
            placed.add(name)
            entries.append(_table_entry(table, classes.get(name), session))
        families.append({**{k: v for k, v in family.items() if k != "tables"}, "tables": entries})

    # A table added to models.py without a family entry still has to appear:
    # silently dropping it would make this page confidently incomplete.
    unclassified = [
        _table_entry(tables[name], classes.get(name), session)
        for name in sorted(set(tables) - placed)
    ]
    if unclassified:
        families.append(
            {
                "key": "unclassified",
                "name": "Not yet classified",
                "lifecycle": "Unknown.",
                "summary": (
                    "Present in the ORM but not assigned to a family in "
                    "datamodel.FAMILIES. Listed here rather than omitted."
                ),
                "tables": unclassified,
            }
        )

    database_url = settings.database_url if settings else ""
    dialect = database_url.split(":", 1)[0] if database_url else ""
    relationships = _relationships()

    return {
        "families": families,
        "relationships": relationships,
        "deployment": {
            "current_dialect": dialect,
            "current_url": _redact_url(database_url),
            "is_production_target": dialect.startswith("postgresql"),
            "targets": list(_TARGETS),
            "notes": list(_NOTES),
        },
        "totals": {
            "tables": len(tables),
            "columns": sum(len(table.columns) for table in tables.values()),
            "foreign_keys": len(relationships),
            "indexes": sum(len(table.indexes) for table in tables.values()),
            "registered_checks": len(CHECK_REGISTRY),
            "rows": (
                sum(entry["row_count"] or 0 for family in families for entry in family["tables"])
                if session is not None
                else None
            ),
        },
    }


#: Managed Postgres on each hyperscaler. The connection string is the only thing
#: that changes — there is no per-cloud code path, and no cloud-specific
#: extension in the schema.
_TARGETS: tuple[dict[str, str], ...] = (
    {
        "platform": "AWS",
        "service": "RDS for PostgreSQL or Aurora PostgreSQL",
        "url": "postgresql+psycopg://<user>@<cluster>.<region>.rds.amazonaws.com:5432/eairn",
        "detail": (
            "Prefer IAM database authentication over a stored password: the task role "
            "mints a short-lived token, so there is no database credential in Secrets "
            "Manager to rotate. Aurora Serverless v2 suits the workload — harvests are "
            "bursty and the API is idle between them."
        ),
    },
    {
        "platform": "Azure",
        "service": "Azure Database for PostgreSQL Flexible Server",
        "url": "postgresql+psycopg://<user>@<server>.postgres.database.azure.com:5432/eairn",
        "detail": (
            "Authenticate the container app's managed identity against the server via "
            "Entra ID, which keeps the same identity already used for the Fabric and "
            "Purview connectors."
        ),
    },
    {
        "platform": "GCP",
        "service": "Cloud SQL for PostgreSQL or AlloyDB",
        "url": "postgresql+psycopg://<user>@<host>:5432/eairn",
        "detail": (
            "Connect through the Cloud SQL Auth Proxy or a private IP; with IAM database "
            "authentication the workload's service account is the database principal."
        ),
    },
)

_NOTES: tuple[dict[str, str], ...] = (
    {
        "heading": "SQLite is for development only",
        "body": (
            "The default URL is a local SQLite file so a laptop or a CI run needs no "
            "external service. It is not a supported production target: this schema "
            "relies on foreign-key cascades and concurrent writers that SQLite handles "
            "differently, and a hosted deployment should set EAIRN_DATABASE_URL to "
            "Postgres before its first harvest."
        ),
    },
    {
        "heading": "Migrations",
        "body": (
            "init_db() calls create_all, which keeps dev and CI one step. A real "
            "deployment runs Alembic instead, so that a rubric already cited by a frozen "
            "snapshot is never altered underneath it."
        ),
    },
    {
        "heading": "No customer rows are stored",
        "body": (
            "Nothing in the canonical family holds table contents. The most sensitive "
            "values in this database are object names, column names and classification "
            "tags. Optional row sampling is off by default, and even when enabled it "
            "requires a per-dataset authorization row recording who approved it and why."
        ),
    },
    {
        "heading": "Retention and tenancy",
        "body": (
            "Every canonical and assessment table is keyed by tenant with an ON DELETE "
            "CASCADE path back to tenants, so removing an organisation removes its "
            "estate and its snapshots in one statement. Snapshots are immutable, so "
            "retention is a deletion policy rather than an update policy."
        ),
    },
    {
        "heading": "Sizing",
        "body": (
            "The canonical family scales with the estate's object count, not with its "
            "data volume: one row per table, per column, per lineage edge. Assessment "
            "rows scale with checks times targets and are the faster-growing family over "
            "time, since each run appends a new immutable snapshot."
        ),
    },
)


def _redact_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    if "@" not in rest:
        return url
    credentials, _, host = rest.rpartition("@")
    user, _, password = credentials.partition(":")
    return f"{scheme}://{user}{':***' if password else ''}@{host}"
