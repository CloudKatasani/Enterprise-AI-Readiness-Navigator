"""Platform connectors beyond the Snowflake reference implementation.

Each class carries the two artefacts a customer needs before anything is
connected -- the least-privilege permission manifest and the exact statement or
API catalog EAIRN will issue -- and can harvest today from a canonical metadata
bundle. Live driver paths land per the product roadmap (Databricks and Fabric in
P2, BigQuery in P3, Oracle in P4); until then a live harvest raises rather than
silently returning an empty estate, because an empty estate would score as
"nothing to see" instead of "not measured".
"""

from __future__ import annotations

from eairn.connectors.base import Connector, HarvestBundle, PermissionGrant, PermissionManifest
from eairn.connectors.canonical_import import load_canonical_bundle


class BundleBackedConnector(Connector):
    """Connector whose live driver is not yet implemented but which can harvest
    a canonical metadata bundle exported by the customer or a delivery partner."""

    roadmap_phase = "P2"
    live_driver: str = ""

    def harvest(self) -> HarvestBundle:
        fixture = self.config.get("bundle") or self.config.get("fixture")
        if fixture:
            bundle = load_canonical_bundle(fixture, connector_key=self.key, platform=self.platform)
            bundle.capabilities &= self.capabilities()
            return bundle
        raise RuntimeError(
            f"{self.display_name}: live harvesting lands in roadmap phase {self.roadmap_phase}"
            + (f" (driver: {self.live_driver})" if self.live_driver else "")
            + ". Configure `bundle=<path to canonical metadata export>` to assess this platform today."
        )

    def preflight(self) -> list[str]:
        if self.config.get("bundle") or self.config.get("fixture"):
            return []
        return [f"no canonical bundle configured and the live driver is not yet available ({self.roadmap_phase})"]


class DatabricksConnector(BundleBackedConnector):
    key = "databricks"
    platform = "databricks"
    display_name = "Databricks (Unity Catalog system tables)"
    roadmap_phase = "P2"
    live_driver = "databricks-sql-connector + Workspace API"

    query_catalog = {
        "tables": """
            SELECT table_catalog, table_schema, table_name, table_type, comment, table_owner
            FROM system.information_schema.tables
        """,
        "columns": """
            SELECT table_catalog, table_schema, table_name, column_name, data_type,
                   ordinal_position, comment
            FROM system.information_schema.columns
        """,
        "table_lineage": """
            SELECT source_table_full_name, target_table_full_name, event_time
            FROM system.access.table_lineage
        """,
        "column_lineage": """
            SELECT source_table_full_name, source_column_name,
                   target_table_full_name, target_column_name
            FROM system.access.column_lineage
        """,
        "grants": """
            SELECT grantee, privilege_type, table_catalog, table_schema, table_name
            FROM system.information_schema.table_privileges
        """,
        "audit": """
            SELECT service_name, action_name, event_date, COUNT(*) AS event_count
            FROM system.access.audit
            GROUP BY service_name, action_name, event_date
        """,
        "usage": """
            SELECT entity_type, entity_id, workspace_id, usage_date, SUM(usage_quantity) AS usage_quantity
            FROM system.billing.usage
            GROUP BY entity_type, entity_id, workspace_id, usage_date
        """,
    }

    def capabilities(self) -> set[str]:
        return {
            "datasets", "columns", "descriptions", "classification", "policies", "lineage",
            "column_lineage", "grants", "usage", "ml_assets", "audit_config",
        }

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal="EAIRN service principal, member of a group with system-table read only",
            grants=(
                PermissionGrant(
                    scope="Unity Catalog",
                    grant="GRANT USE CATALOG, USE SCHEMA ON CATALOG <catalog> TO `eairn-readonly`",
                    purpose="Enumerate catalogs, schemas and tables through information_schema",
                ),
                PermissionGrant(
                    scope="system catalog",
                    grant="GRANT SELECT ON SCHEMA system.access TO `eairn-readonly`",
                    purpose="Read lineage and audit system tables",
                ),
                PermissionGrant(
                    scope="workspace API",
                    grant="Workspace user with can-view on MLflow experiments and registered models",
                    purpose="Assess model registry and serving-endpoint governance",
                ),
            ),
            reads_row_data=False,
            notes=(
                "No SELECT on customer data tables is requested. hive_metastore residue is detected "
                "through catalog enumeration, not by reading legacy tables."
            ),
        )


class FabricConnector(BundleBackedConnector):
    key = "fabric"
    platform = "fabric"
    display_name = "Microsoft Fabric (Admin + Purview APIs)"
    roadmap_phase = "P2"
    live_driver = "Microsoft Graph + Fabric Admin API + Purview API"

    api_catalog = {
        "workspaces": "GET https://api.fabric.microsoft.com/v1/admin/workspaces",
        "items": "GET https://api.fabric.microsoft.com/v1/admin/items?type={item_type}",
        "semantic_models": "GET https://api.powerbi.com/v1.0/myorg/admin/datasets",
        "sensitivity_labels": "GET https://api.fabric.microsoft.com/v1/admin/items?$expand=sensitivityLabel",
        "purview_scans": "GET https://{account}.purview.azure.com/scan/datasources?api-version=2023-09-01",
        "purview_classifications": "GET https://{account}.purview.azure.com/catalog/api/atlas/v2/types/classificationdef",
        "domains": "GET https://api.fabric.microsoft.com/v1/admin/domains",
        "dlp_policies": "GET https://graph.microsoft.com/v1.0/security/dataLossPreventionPolicies",
    }

    def capabilities(self) -> set[str]:
        return {
            "datasets", "columns", "descriptions", "classification", "policies",
            "semantic_models", "kpi_definitions", "governance_program", "audit_config",
        }

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal="Entra ID application with tenant-metadata read scopes",
            grants=(
                PermissionGrant(
                    scope="Microsoft Graph",
                    grant="Directory.Read.All (application)",
                    purpose="Resolve workspace ownership and domain assignment",
                ),
                PermissionGrant(
                    scope="Fabric Admin API",
                    grant="Tenant.Read.All (application), admin consent required",
                    purpose="Enumerate workspaces, items, labels and semantic models",
                ),
                PermissionGrant(
                    scope="Purview",
                    grant="Data Reader on the Purview account",
                    purpose="Read scan coverage, classifications and glossary linkage",
                ),
            ),
            reads_row_data=False,
            notes="Tenant metadata only; no dataset content and no report data is read.",
        )


class BigQueryConnector(BundleBackedConnector):
    key = "bigquery"
    platform = "bigquery"
    display_name = "Google BigQuery (INFORMATION_SCHEMA + Dataplex)"
    roadmap_phase = "P3"
    live_driver = "google-cloud-bigquery + Dataplex + Data Lineage APIs"

    query_catalog = {
        "tables": """
            SELECT table_catalog, table_schema, table_name, table_type, creation_time
            FROM `region-us`.INFORMATION_SCHEMA.TABLES
        """,
        "table_options": """
            SELECT table_catalog, table_schema, table_name, option_name, option_value
            FROM `region-us`.INFORMATION_SCHEMA.TABLE_OPTIONS
            WHERE option_name = 'description'
        """,
        "columns": """
            SELECT table_catalog, table_schema, table_name, field_path, data_type, description
            FROM `region-us`.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS
        """,
        "jobs": """
            SELECT referenced_table.project_id, referenced_table.dataset_id, referenced_table.table_id,
                   DATE(creation_time) AS usage_date, COUNT(*) AS query_count,
                   COUNT(DISTINCT user_email) AS distinct_users
            FROM `region-us`.INFORMATION_SCHEMA.JOBS
            CROSS JOIN UNNEST(referenced_tables) AS referenced_table
            WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
            GROUP BY 1, 2, 3, 4
        """,
    }

    api_catalog = {
        "policy_tags": "GET https://datacatalog.googleapis.com/v1/projects/{project}/locations/{location}/taxonomies",
        "dataplex_scans": "GET https://dataplex.googleapis.com/v1/projects/{project}/locations/{location}/dataScans",
        # Search-only POST: the Data Lineage API exposes link search over POST and
        # the endpoint has been reviewed as non-mutating.
        "lineage": "POST https://datalineage.googleapis.com/v1/projects/{project}/locations/{location}:searchLinks",
    }

    read_only_post_endpoints = (
        "https://datalineage.googleapis.com/v1/projects/{project}/locations/{location}:searchLinks",
    )

    def capabilities(self) -> set[str]:
        return {
            "datasets", "columns", "descriptions", "classification", "policies", "lineage",
            "usage", "dq_monitors", "ml_assets", "audit_config",
        }

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal="Dedicated GCP service account, keyless via workload identity federation",
            grants=(
                PermissionGrant(
                    scope="project",
                    grant="roles/bigquery.metadataViewer",
                    purpose="Read table and column metadata without table data access",
                ),
                PermissionGrant(
                    scope="project",
                    grant="roles/datacatalog.viewer",
                    purpose="Read taxonomies, policy tags and entry descriptions",
                ),
                PermissionGrant(
                    scope="project",
                    grant="roles/dataplex.viewer",
                    purpose="Read lake/zone organisation and data-quality scan results",
                ),
                PermissionGrant(
                    scope="project",
                    grant="roles/datalineage.viewer",
                    purpose="Read lineage links including cross-project edges",
                ),
            ),
            reads_row_data=False,
            notes=(
                "roles/bigquery.dataViewer is deliberately NOT requested -- metadataViewer cannot "
                "read table contents."
            ),
        )


class OracleConnector(BundleBackedConnector):
    key = "oracle"
    platform = "oracle"
    display_name = "Oracle Exadata (data dictionary + Unified Audit)"
    roadmap_phase = "P4"
    live_driver = "python-oracledb (thin mode)"

    query_catalog = {
        "tables": """
            SELECT owner, table_name, num_rows, last_analyzed
            FROM dba_tables
        """,
        "table_comments": """
            SELECT owner, table_name, comments
            FROM dba_tab_comments
        """,
        "columns": """
            SELECT owner, table_name, column_name, data_type, column_id
            FROM dba_tab_columns
        """,
        "column_comments": """
            SELECT owner, table_name, column_name, comments
            FROM dba_col_comments
        """,
        "dependencies": """
            SELECT owner, name, referenced_owner, referenced_name, referenced_type
            FROM dba_dependencies
        """,
        "redaction": """
            SELECT object_owner, object_name, column_name, function_type
            FROM redaction_columns
        """,
        "audit_policies": """
            SELECT policy_name, enabled_option, entity_name, success, failure
            FROM audit_unified_enabled_policies
        """,
        "supplemental_logging": """
            SELECT owner, table_name, log_group_type
            FROM dba_log_groups
        """,
        "invalid_objects": """
            SELECT owner, object_name, object_type, status
            FROM dba_objects
            WHERE status <> 'VALID'
        """,
    }

    def capabilities(self) -> set[str]:
        return {"datasets", "columns", "descriptions", "classification", "policies", "lineage", "audit_config"}

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal="EAIRN_RO database account",
            grants=(
                PermissionGrant(
                    scope="database",
                    grant="GRANT CREATE SESSION TO EAIRN_RO",
                    purpose="Connect to the instance",
                ),
                PermissionGrant(
                    scope="database",
                    grant="GRANT SELECT_CATALOG_ROLE TO EAIRN_RO",
                    purpose="Read DBA_/ALL_ dictionary views",
                ),
                PermissionGrant(
                    scope="database",
                    grant="GRANT SELECT ON AUDSYS.AUD$UNIFIED TO EAIRN_RO (or AUDIT_VIEWER)",
                    purpose="Read Unified Audit policy inventory",
                ),
            ),
            reads_row_data=False,
            notes=(
                "SELECT ANY TABLE is never requested. Dictionary views expose structure and policy "
                "metadata only."
            ),
        )
