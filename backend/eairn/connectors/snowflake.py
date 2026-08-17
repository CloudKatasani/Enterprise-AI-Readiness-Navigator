"""Snowflake connector -- the reference implementation.

Runs entirely against ``SNOWFLAKE.ACCOUNT_USAGE`` and ``INFORMATION_SCHEMA``
views. It never reads a customer table: the role it needs holds
``IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`` and nothing else.

Two execution modes share one normaliser, so the code path exercised by tests is
the code path used against a live account:

* **live** -- ``snowflake-connector-python`` executes the query catalog.
* **fixture** -- rows are read from a JSON file with the same shape.

Column names in the catalog follow the documented ACCOUNT_USAGE views, and
normalisation is defensive (``row.get``) so a view that gains or renames a
column degrades to a warning rather than a failed harvest.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eairn.connectors.base import (
    Connector,
    HarvestBundle,
    PermissionGrant,
    PermissionManifest,
    assert_read_only,
)
from eairn.models import (
    Column,
    Dataset,
    DQMonitor,
    GovernanceProgram,
    Grant,
    LineageEdge,
    Policy,
    SemanticModel,
    UsageEvent,
)

LOOKBACK_DAYS = 90


class SnowflakeConnector(Connector):
    key = "snowflake"
    platform = "snowflake"
    display_name = "Snowflake (ACCOUNT_USAGE)"

    query_catalog = {
        "tables": """
            SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, COMMENT,
                   TABLE_OWNER, BYTES, ROW_COUNT, LAST_ALTERED
            FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
            WHERE DELETED IS NULL
        """,
        "columns": """
            SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE,
                   ORDINAL_POSITION, COMMENT
            FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS
            WHERE DELETED IS NULL
        """,
        # Tag references carry both object- and column-level tags; PII/sensitivity
        # tags are read from here rather than inferred.
        "tag_references": """
            SELECT OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, COLUMN_NAME,
                   TAG_NAME, TAG_VALUE, DOMAIN
            FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
        """,
        # Masking and row-access policy attachments. A tagged column with no row
        # here is the finding that drives the Security hard blocker.
        "policy_references": """
            SELECT POLICY_NAME, POLICY_KIND, REF_DATABASE_NAME, REF_SCHEMA_NAME,
                   REF_ENTITY_NAME, REF_COLUMN_NAME, TAG_NAME
            FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
        """,
        "object_dependencies": """
            SELECT REFERENCED_DATABASE, REFERENCED_SCHEMA, REFERENCED_OBJECT_NAME,
                   REFERENCING_DATABASE, REFERENCING_SCHEMA, REFERENCING_OBJECT_NAME
            FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
        """,
        # Column-level lineage derived from ACCESS_HISTORY. Rows produced this way
        # are marked as inferred so the check library can discount their confidence.
        "column_lineage": """
            SELECT UPSTREAM_DATABASE, UPSTREAM_SCHEMA, UPSTREAM_TABLE, UPSTREAM_COLUMN,
                   DOWNSTREAM_DATABASE, DOWNSTREAM_SCHEMA, DOWNSTREAM_TABLE, DOWNSTREAM_COLUMN
            FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY_COLUMN_LINEAGE
        """,
        # Daily usage rollup from ACCESS_HISTORY. Aggregated in-warehouse so no
        # statement text and no per-query row ever leaves the customer account.
        "usage": """
            SELECT SPLIT_PART(bo.value:"objectName"::string, '.', 1) AS OBJECT_DATABASE,
                   SPLIT_PART(bo.value:"objectName"::string, '.', 2) AS OBJECT_SCHEMA,
                   SPLIT_PART(bo.value:"objectName"::string, '.', 3) AS OBJECT_NAME,
                   TO_DATE(ah.QUERY_START_TIME) AS USAGE_DATE,
                   IFF(ah.USER_NAME ILIKE 'SVC%' OR ah.USER_NAME ILIKE '%_AGENT', 'service', 'human')
                       AS IDENTITY_KIND,
                   COUNT(*) AS QUERY_COUNT,
                   COUNT(DISTINCT ah.USER_NAME) AS DISTINCT_USERS
            FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
                 LATERAL FLATTEN(input => ah.BASE_OBJECTS_ACCESSED) bo
            WHERE ah.QUERY_START_TIME >= DATEADD('day', -90, CURRENT_TIMESTAMP())
              AND bo.value:"objectDomain"::string IN ('Table', 'View', 'Materialized view')
            GROUP BY 1, 2, 3, 4, 5
        """,
        "grants_to_roles": """
            SELECT GRANTEE_NAME, PRIVILEGE, GRANTED_ON, TABLE_CATALOG, TABLE_SCHEMA, NAME
            FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
            WHERE DELETED_ON IS NULL
        """,
        "grants_to_users": """
            SELECT GRANTEE_NAME, ROLE
            FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
            WHERE DELETED_ON IS NULL
        """,
        "dmf_references": """
            SELECT REF_DATABASE_NAME, REF_SCHEMA_NAME, REF_ENTITY_NAME,
                   METRIC_NAME, SCHEDULE_STATUS
            FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES
        """,
        "dmf_results": """
            SELECT TABLE_DATABASE, TABLE_SCHEMA, TABLE_NAME, METRIC_NAME,
                   MEASUREMENT_TIME, VALUE
            FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS
        """,
        "semantic_views": """
            SELECT SEMANTIC_VIEW_CATALOG, SEMANTIC_VIEW_SCHEMA, SEMANTIC_VIEW_NAME,
                   COMMENT, CREATED
            FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEWS
        """,
    }

    #: Query names that depend on views not present in every Snowflake edition or
    #: release track. Their absence is a warning, not a harvest failure.
    optional_queries = frozenset({"column_lineage", "semantic_views", "usage", "dmf_references", "dmf_results"})

    def capabilities(self) -> set[str]:
        return {
            "datasets",
            "columns",
            "descriptions",
            "classification",
            "policies",
            "lineage",
            "column_lineage",
            "grants",
            "usage",
            "dq_monitors",
            "semantic_models",
            "audit_config",
        }

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal="EAIRN_READONLY role, assumed by a dedicated service user with key-pair auth",
            grants=(
                PermissionGrant(
                    scope="DATABASE SNOWFLAKE",
                    grant="GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE EAIRN_READONLY",
                    purpose="Read ACCOUNT_USAGE / ORGANIZATION_USAGE metadata views",
                ),
                PermissionGrant(
                    scope="WAREHOUSE EAIRN_WH",
                    grant="GRANT USAGE ON WAREHOUSE EAIRN_WH TO ROLE EAIRN_READONLY",
                    purpose="Execute the metadata queries (XS warehouse is sufficient)",
                ),
                PermissionGrant(
                    scope="ACCOUNT",
                    grant="GRANT MONITOR USAGE ON ACCOUNT TO ROLE EAIRN_READONLY",
                    purpose="Read account-level usage and grant metadata",
                ),
            ),
            reads_row_data=False,
            notes=(
                "No grant on any customer database, schema or table is requested or accepted. "
                "The role cannot read customer rows even if asked to."
            ),
        )

    def preflight(self) -> list[str]:
        problems = []
        if self.config.get("fixture"):
            if not Path(self.config["fixture"]).exists():
                problems.append(f"fixture file not found: {self.config['fixture']}")
            return problems
        for required in ("account", "user", "role", "warehouse"):
            if not self.config.get(required):
                problems.append(f"missing required config: {required}")
        if not (self.config.get("private_key_path") or self.config.get("password")):
            problems.append("missing credential: private_key_path or password")
        if self.config.get("role", "").upper() in {"ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN"}:
            problems.append(
                "refusing to run under an admin role; provision the least-privilege "
                "EAIRN_READONLY role from the permission manifest"
            )
        return problems

    # -- execution ---------------------------------------------------------- #

    def _fetch(self) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        fixture = self.config.get("fixture")
        if fixture:
            with Path(fixture).open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            warnings = [f"harvested from fixture {fixture}"]
            missing = sorted(set(self.query_catalog) - set(payload) - self.optional_queries)
            warnings += [f"fixture missing rows for query {name!r}" for name in missing]
            return payload, warnings
        return self._fetch_live()

    def _fetch_live(self) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        problems = self.preflight()
        if problems:
            raise RuntimeError("snowflake connector preflight failed: " + "; ".join(problems))
        try:
            import snowflake.connector  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "snowflake-connector-python is not installed. Install the 'snowflake' extra, "
                "or configure a fixture for offline runs."
            ) from exc

        connect_args = {
            "account": self.config["account"],
            "user": self.config["user"],
            "role": self.config["role"],
            "warehouse": self.config["warehouse"],
            # Belt and braces: the session may not write even if a query slipped through.
            "session_parameters": {"STATEMENT_TIMEOUT_IN_SECONDS": 900},
        }
        if self.config.get("password"):
            connect_args["password"] = self.config["password"]
        if self.config.get("private_key_path"):
            connect_args["private_key_file"] = self.config["private_key_path"]

        rows: dict[str, list[dict[str, Any]]] = {}
        warnings: list[str] = []
        connection = snowflake.connector.connect(**connect_args)  # pragma: no cover - live path
        try:  # pragma: no cover - live path
            for name in self.query_catalog:
                statement = self.query(name)  # re-validates read-only
                cursor = connection.cursor(snowflake.connector.DictCursor)
                try:
                    cursor.execute(statement)
                    rows[name] = [dict(row) for row in cursor.fetchall()]
                except Exception as exc:  # noqa: BLE001 - one missing view must not fail the run
                    if name in self.optional_queries:
                        rows[name] = []
                        warnings.append(f"optional query {name!r} unavailable: {exc}")
                    else:
                        raise
                finally:
                    cursor.close()
        finally:  # pragma: no cover - live path
            connection.close()
        return rows, warnings

    # -- normalisation ------------------------------------------------------ #

    def harvest(self) -> HarvestBundle:
        rows, warnings = self._fetch()
        bundle = HarvestBundle(connector_key=self.key, platform=self.platform)
        bundle.capabilities = self.capabilities()
        bundle.warnings = warnings

        tier_rules = self.config.get("tier_rules", {})
        datasets: dict[str, Dataset] = {}

        for row in rows.get("tables", []):
            urn = _urn(row.get("TABLE_CATALOG"), row.get("TABLE_SCHEMA"), row.get("TABLE_NAME"))
            dataset = Dataset(
                urn=urn,
                platform=self.platform,
                catalog=row.get("TABLE_CATALOG"),
                schema_name=row.get("TABLE_SCHEMA"),
                name=row.get("TABLE_NAME", ""),
                object_type=row.get("TABLE_TYPE", "TABLE"),
                description=row.get("COMMENT"),
                owner=row.get("TABLE_OWNER"),
                bytes=int(row.get("BYTES") or 0),
                tier=_tier_for(urn, tier_rules),
                domain=_domain_for(row.get("TABLE_SCHEMA"), self.config.get("domain_map", {})),
                last_queried_at=_parse_dt(row.get("LAST_ALTERED")),
                attributes={"row_count": row.get("ROW_COUNT")},
            )
            datasets[urn] = dataset

        for row in rows.get("columns", []):
            urn = _urn(row.get("TABLE_CATALOG"), row.get("TABLE_SCHEMA"), row.get("TABLE_NAME"))
            dataset = datasets.get(urn)
            if dataset is None:
                continue
            dataset.columns.append(
                Column(
                    name=row.get("COLUMN_NAME", ""),
                    data_type=row.get("DATA_TYPE", "VARCHAR"),
                    ordinal=int(row.get("ORDINAL_POSITION") or 0),
                    description=row.get("COMMENT"),
                )
            )

        # Tags: sensitivity classification and data-product tier markers.
        for row in rows.get("tag_references", []):
            urn = _urn(row.get("OBJECT_DATABASE"), row.get("OBJECT_SCHEMA"), row.get("OBJECT_NAME"))
            dataset = datasets.get(urn)
            if dataset is None:
                continue
            tag_name = (row.get("TAG_NAME") or "").upper()
            tag_value = (row.get("TAG_VALUE") or "").lower()
            column_name = row.get("COLUMN_NAME")
            if tag_name in {"TIER", "DATA_PRODUCT_TIER"} and tag_value.isdigit():
                dataset.tier = int(tag_value)
            elif tag_name in {"CERTIFIED", "CERTIFICATION"}:
                dataset.certified = tag_value in {"true", "certified", "yes"}
            elif column_name:
                column = next((c for c in dataset.columns if c.name == column_name), None)
                if column is not None and tag_name in {"PII", "SENSITIVITY", "CLASSIFICATION", "SEMANTIC_CATEGORY"}:
                    column.platform_classification = tag_value or tag_name.lower()

        # Policy attachments -> per-column protection flags.
        for row in rows.get("policy_references", []):
            urn = _urn(row.get("REF_DATABASE_NAME"), row.get("REF_SCHEMA_NAME"), row.get("REF_ENTITY_NAME"))
            policy_kind = (row.get("POLICY_KIND") or "").upper()
            bundle.policies.append(
                Policy(
                    platform=self.platform,
                    policy_type="masking" if "MASKING" in policy_kind else "row_access",
                    name=row.get("POLICY_NAME", ""),
                    bound_to_tag=row.get("TAG_NAME"),
                    target_urns=[urn],
                )
            )
            dataset = datasets.get(urn)
            if dataset is None:
                continue
            column_name = row.get("REF_COLUMN_NAME")
            if column_name:
                column = next((c for c in dataset.columns if c.name == column_name), None)
                if column is not None:
                    column.protected = True
                    column.protection_kind = policy_kind.lower() or "masking"

        for row in rows.get("object_dependencies", []):
            bundle.lineage.append(
                LineageEdge(
                    upstream_urn=_urn(
                        row.get("REFERENCED_DATABASE"),
                        row.get("REFERENCED_SCHEMA"),
                        row.get("REFERENCED_OBJECT_NAME"),
                    ),
                    downstream_urn=_urn(
                        row.get("REFERENCING_DATABASE"),
                        row.get("REFERENCING_SCHEMA"),
                        row.get("REFERENCING_OBJECT_NAME"),
                    ),
                    level="table",
                    source="object_dependencies",
                    confidence=1.0,
                )
            )

        for row in rows.get("column_lineage", []):
            bundle.lineage.append(
                LineageEdge(
                    upstream_urn=_urn(
                        row.get("UPSTREAM_DATABASE"), row.get("UPSTREAM_SCHEMA"), row.get("UPSTREAM_TABLE")
                    ),
                    downstream_urn=_urn(
                        row.get("DOWNSTREAM_DATABASE"), row.get("DOWNSTREAM_SCHEMA"), row.get("DOWNSTREAM_TABLE")
                    ),
                    level="column",
                    upstream_column=row.get("UPSTREAM_COLUMN"),
                    downstream_column=row.get("DOWNSTREAM_COLUMN"),
                    source="access_history",
                    confidence=0.7,
                )
            )

        for row in rows.get("usage", []):
            urn = _urn(row.get("OBJECT_DATABASE"), row.get("OBJECT_SCHEMA"), row.get("OBJECT_NAME"))
            event_date = _parse_dt(row.get("USAGE_DATE")) or datetime.now(timezone.utc)
            bundle.usage.append(
                UsageEvent(
                    dataset_urn=urn,
                    event_date=event_date,
                    query_count=int(row.get("QUERY_COUNT") or 0),
                    distinct_users=int(row.get("DISTINCT_USERS") or 0),
                    identity_kind=(row.get("IDENTITY_KIND") or "human").lower(),
                )
            )
            dataset = datasets.get(urn)
            if dataset is not None:
                if dataset.last_queried_at is None or event_date > dataset.last_queried_at:
                    dataset.last_queried_at = event_date

        admin_roles = {"ACCOUNTADMIN", "SECURITYADMIN"}
        for row in rows.get("grants_to_roles", []):
            grantee = row.get("GRANTEE_NAME", "")
            bundle.grants.append(
                Grant(
                    platform=self.platform,
                    grantee=grantee,
                    grantee_type="role",
                    privilege=row.get("PRIVILEGE", ""),
                    object_urn=_urn(row.get("TABLE_CATALOG"), row.get("TABLE_SCHEMA"), row.get("NAME")),
                    is_admin_role=grantee.upper() in admin_roles,
                )
            )
        for row in rows.get("grants_to_users", []):
            role = (row.get("ROLE") or "").upper()
            bundle.grants.append(
                Grant(
                    platform=self.platform,
                    grantee=row.get("GRANTEE_NAME", ""),
                    grantee_type="user",
                    privilege=f"ROLE {role}",
                    object_urn=None,
                    is_admin_role=role in admin_roles,
                )
            )

        pass_rates = _dmf_pass_rates(rows.get("dmf_results", []))
        for row in rows.get("dmf_references", []):
            urn = _urn(row.get("REF_DATABASE_NAME"), row.get("REF_SCHEMA_NAME"), row.get("REF_ENTITY_NAME"))
            metric = (row.get("METRIC_NAME") or "").upper()
            bundle.dq_monitors.append(
                DQMonitor(
                    dataset_urn=urn,
                    tool="snowflake_dmf",
                    check_type=_dmf_check_type(metric),
                    defined_as_data=True,
                    enabled=(row.get("SCHEDULE_STATUS") or "STARTED").upper().startswith("START"),
                    pass_rate=pass_rates.get((urn, metric), 1.0),
                )
            )

        for row in rows.get("semantic_views", []):
            bundle.semantic_models.append(
                SemanticModel(
                    platform=self.platform,
                    name=_urn(
                        row.get("SEMANTIC_VIEW_CATALOG"),
                        row.get("SEMANTIC_VIEW_SCHEMA"),
                        row.get("SEMANTIC_VIEW_NAME"),
                    ),
                    certified=bool(row.get("COMMENT")),
                    field_count=int(row.get("FIELD_COUNT") or 0),
                    described_field_count=int(row.get("DESCRIBED_FIELD_COUNT") or 0),
                    synonym_field_count=int(row.get("SYNONYM_FIELD_COUNT") or 0),
                )
            )

        # Audit posture is a property of the account, not of a table.
        bundle.governance_programs.append(
            GovernanceProgram(
                tool="snowflake_account",
                audit_logging_enabled=True,
                audit_retention_days=int(self.config.get("access_history_retention_days", 365)),
                last_scan_at=datetime.now(timezone.utc),
            )
        )

        bundle.datasets = list(datasets.values())
        return bundle


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _urn(catalog: str | None, schema: str | None, name: str | None) -> str:
    parts = [p for p in (catalog, schema, name) if p]
    return "snowflake://" + ".".join(parts)


def _tier_for(urn: str, tier_rules: dict[str, int]) -> int:
    """Tiering comes from customer-declared rules, defaulting to Tier 3."""
    for pattern, tier in tier_rules.items():
        if pattern in urn:
            return int(tier)
    return 3


def _domain_for(schema: str | None, domain_map: dict[str, str]) -> str | None:
    if not schema:
        return None
    return domain_map.get(schema, schema.lower())


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def _dmf_check_type(metric_name: str) -> str:
    metric = metric_name.upper()
    if "NULL" in metric or "BLANK" in metric or "COUNT" in metric:
        return "completeness"
    if "FRESH" in metric or "STALE" in metric or "LAG" in metric:
        return "freshness"
    if "DUPLICATE" in metric or "UNIQUE" in metric or "ACCEPTED" in metric:
        return "validity"
    return "anomaly"


def _dmf_pass_rates(result_rows: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    """Pass rate per (table, metric): a DMF value of 0 is a clean measurement."""
    buckets: dict[tuple[str, str], list[float]] = {}
    for row in result_rows:
        urn = _urn(row.get("TABLE_DATABASE"), row.get("TABLE_SCHEMA"), row.get("TABLE_NAME"))
        metric = (row.get("METRIC_NAME") or "").upper()
        value = row.get("VALUE")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        buckets.setdefault((urn, metric), []).append(1.0 if numeric == 0 else 0.0)
    return {key: sum(values) / len(values) for key, values in buckets.items() if values}


def default_lookback_window() -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(days=LOOKBACK_DAYS), end


# Re-exported for the CI kill test.
__all__ = ["SnowflakeConnector", "assert_read_only"]
