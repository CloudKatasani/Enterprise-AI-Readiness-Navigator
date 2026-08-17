"""Governance and data-quality tool connectors (blueprint S11, S12).

These tools are harvested as evidence sources *and* scored as subjects: EAIRN
reads their classifications, glossaries, rules and incident histories, then asks
whether the programme behind them is operationally alive.

Each connector publishes its API catalog and least-privilege manifest, and can
harvest from a canonical metadata bundle today; live API drivers follow the
roadmap phase named on each class.
"""

from __future__ import annotations

from eairn.connectors.base import PermissionGrant, PermissionManifest
from eairn.connectors.platforms import BundleBackedConnector


class _ToolConnector(BundleBackedConnector):
    """Shared shape for third-party governance / DQ tools."""

    principal = "Read-only API token issued to an EAIRN integration user"
    manifest_grants: tuple[tuple[str, str, str], ...] = ()
    manifest_notes = "Read-only API scopes; EAIRN never writes back to the tool."

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal=self.principal,
            grants=tuple(PermissionGrant(*grant) for grant in self.manifest_grants),
            reads_row_data=False,
            notes=self.manifest_notes,
        )


# --------------------------------------------------------------------------- #
# Governance tools
# --------------------------------------------------------------------------- #


class CollibraConnector(_ToolConnector):
    key = "collibra"
    platform = "collibra"
    display_name = "Collibra Data Intelligence Cloud"
    roadmap_phase = "P1"

    api_catalog = {
        "assets": "GET {host}/rest/2.0/assets",
        "domains": "GET {host}/rest/2.0/domains",
        "responsibilities": "GET {host}/rest/2.0/responsibilities",
        "workflow_instances": "GET {host}/rest/2.0/workflowInstances",
        "attributes": "GET {host}/rest/2.0/attributes",
        "relations": "GET {host}/rest/2.0/relations",
    }
    manifest_grants = (
        ("Collibra", "Read-only role on the relevant communities and domains", "Harvest assets, owners and workflows"),
        ("Collibra", "Workflow read scope", "Measure certification throughput and steward latency"),
    )

    def capabilities(self) -> set[str]:
        return {"datasets", "classification", "governance_program"}


class AlationConnector(_ToolConnector):
    key = "alation"
    platform = "alation"
    display_name = "Alation Data Catalog"
    roadmap_phase = "P2"

    api_catalog = {
        "tables": "GET {host}/integration/v2/table/",
        "columns": "GET {host}/integration/v2/column/",
        "stewards": "GET {host}/integration/v2/custom_field_value/",
        "query_log_top_objects": "GET {host}/integration/v1/query_log/top_objects/",
        "articles": "GET {host}/integration/v1/article/",
    }
    manifest_grants = (
        ("Alation", "Viewer API token", "Harvest catalog curation, stewardship and query-log intelligence"),
    )

    def capabilities(self) -> set[str]:
        return {"datasets", "descriptions", "usage", "governance_program"}


class PurviewConnector(_ToolConnector):
    key = "purview"
    platform = "purview"
    display_name = "Microsoft Purview"
    roadmap_phase = "P1"

    api_catalog = {
        "scans": "GET https://{account}.purview.azure.com/scan/datasources?api-version=2023-09-01",
        "classifications": "GET https://{account}.purview.azure.com/catalog/api/atlas/v2/types/classificationdef",
        "glossary": "GET https://{account}.purview.azure.com/catalog/api/atlas/v2/glossary",
        "entity_search": "POST https://{account}.purview.azure.com/catalog/api/search/query?api-version=2023-09-01",
        "lineage": "GET https://{account}.purview.azure.com/catalog/api/atlas/v2/lineage/{guid}",
    }
    read_only_post_endpoints = (
        "https://{account}.purview.azure.com/catalog/api/search/query?api-version=2023-09-01",
    )
    manifest_grants = (
        ("Purview", "Data Reader on the Purview account", "Read scans, classifications, glossary and lineage"),
    )

    def capabilities(self) -> set[str]:
        return {"datasets", "classification", "lineage", "governance_program"}


class AtlanConnector(_ToolConnector):
    key = "atlan"
    platform = "atlan"
    display_name = "Atlan"
    roadmap_phase = "P2"

    api_catalog = {
        "entity_search": "POST {host}/api/meta/search/indexsearch",
        "glossary": "GET {host}/api/meta/types/typedefs?type=glossary",
        "lineage": "GET {host}/api/meta/lineage/{guid}",
    }
    read_only_post_endpoints = ("{host}/api/meta/search/indexsearch",)
    manifest_grants = (
        ("Atlan", "API token with member (read) role", "Harvest assets, README coverage and lineage"),
    )

    def capabilities(self) -> set[str]:
        return {"datasets", "descriptions", "classification", "lineage", "governance_program"}


class InformaticaCDGCConnector(_ToolConnector):
    key = "informatica_cdgc"
    platform = "informatica"
    display_name = "Informatica EDC / CDGC"
    roadmap_phase = "P3"

    api_catalog = {
        "objects": "GET {host}/access/2/catalog/data/objects",
        "relationships": "GET {host}/access/2/catalog/data/relationships",
        "business_terms": "GET {host}/access/2/catalog/models/attributes",
    }
    manifest_grants = (
        ("Informatica", "Catalog read-only user", "Harvest scans, curation state and term-to-column linkage"),
    )

    def capabilities(self) -> set[str]:
        return {"datasets", "classification", "lineage", "governance_program"}


# --------------------------------------------------------------------------- #
# Data-quality tools
# --------------------------------------------------------------------------- #


class MonteCarloConnector(_ToolConnector):
    key = "monte_carlo"
    platform = "monte_carlo"
    display_name = "Monte Carlo"
    roadmap_phase = "P3"

    api_catalog = {
        "monitors": "POST {host}/graphql (query getMonitors)",
        "incidents": "POST {host}/graphql (query getIncidents)",
        "tables": "POST {host}/graphql (query getTables)",
    }
    read_only_post_endpoints = (
        "{host}/graphql (query getMonitors)",
        "{host}/graphql (query getIncidents)",
        "{host}/graphql (query getTables)",
    )
    manifest_grants = (
        ("Monte Carlo", "API key with viewer role", "Harvest monitors, incidents and lineage-aware alerting"),
    )
    manifest_notes = (
        "GraphQL queries only -- no mutations. The declared endpoints are query documents reviewed "
        "as read-only."
    )

    def capabilities(self) -> set[str]:
        return {"dq_monitors", "dq_incidents"}


class GreatExpectationsConnector(_ToolConnector):
    key = "great_expectations"
    platform = "great_expectations"
    display_name = "Great Expectations"
    roadmap_phase = "P3"

    api_catalog = {
        "suites": "GET {host}/api/v1/expectation-suites",
        "validation_results": "GET {host}/api/v1/validation-results",
        "checkpoints": "GET {host}/api/v1/checkpoints",
    }
    manifest_grants = (
        ("Great Expectations", "Read token or read access to the data-docs store", "Harvest suites and validations"),
    )

    def capabilities(self) -> set[str]:
        return {"dq_monitors", "dq_incidents"}


class SodaConnector(_ToolConnector):
    key = "soda"
    platform = "soda"
    display_name = "Soda Cloud"
    roadmap_phase = "P3"

    api_catalog = {
        "checks": "GET {host}/api/v1/checks",
        "scans": "GET {host}/api/v1/scans",
        "contracts": "GET {host}/api/v1/contracts",
    }
    manifest_grants = (("Soda Cloud", "API key (read)", "Harvest checks-as-code, scans and data contracts"),)

    def capabilities(self) -> set[str]:
        return {"dq_monitors", "dq_incidents"}


class AtaccamaConnector(_ToolConnector):
    key = "ataccama"
    platform = "ataccama"
    display_name = "Ataccama ONE"
    roadmap_phase = "P4"

    api_catalog = {
        "rules": "GET {host}/api/v1/rules",
        "anomalies": "GET {host}/api/v1/anomalies",
        "issues": "GET {host}/api/v1/issues",
    }
    manifest_grants = (("Ataccama ONE", "Read-only API user", "Harvest rules, anomaly models and issue workflows"),)

    def capabilities(self) -> set[str]:
        return {"dq_monitors", "dq_incidents", "governance_program"}
