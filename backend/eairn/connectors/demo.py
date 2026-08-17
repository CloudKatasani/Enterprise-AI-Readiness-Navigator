"""Demo connector: a deterministic synthetic estate.

Used for demonstrations, for the seeded portal, and as the fixture behind the
golden scoring tests. It is deterministic by construction -- a fixed seed and a
fixed iteration order -- so the same harvest always produces the same evidence,
the same scores and the same snapshot hash.

The estate it describes is a mid-size financial-services enterprise partway
through a governance programme: strong warehouse hygiene, patchy metadata, an
unfinished PII protection rollout, agents running under a shared identity, and a
RAG pilot indexing content whose ACLs do not propagate. That shape exercises
every hard-blocker override in the rubric.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from eairn.connectors.base import Connector, HarvestBundle, PermissionGrant, PermissionManifest
from eairn.models import (
    AgentAsset,
    Column,
    Dataset,
    DQIncident,
    DQMonitor,
    GovernanceProgram,
    Grant,
    KPIDefinition,
    LineageEdge,
    MLAsset,
    Policy,
    RAGCorpus,
    SemanticModel,
    UsageEvent,
)

SEED = 20260817
HARVEST_ANCHOR = datetime(2026, 8, 17, 9, 0, 0, tzinfo=timezone.utc)

DOMAINS = {
    "SALES": ("sales", 1),
    "FINANCE": ("finance", 1),
    "RISK": ("risk", 1),
    "CUSTOMER": ("customer", 1),
    "MARKETING": ("marketing", 2),
    "OPERATIONS": ("operations", 2),
    "HR": ("hr", 2),
    "SANDBOX": ("sandbox", 3),
    "STAGING": ("staging", 3),
}

TABLE_STEMS = [
    "ORDERS", "ORDER_LINES", "CUSTOMERS", "ACCOUNTS", "TRANSACTIONS", "BALANCES",
    "POSITIONS", "EXPOSURES", "CAMPAIGNS", "LEADS", "EMPLOYEES", "PAYROLL",
    "INVOICES", "PAYMENTS", "PRODUCTS", "PRICES", "CHANNELS", "BRANCHES",
    "RISK_SCORES", "LIMITS", "COLLATERAL", "SETTLEMENTS", "TICKETS", "SESSIONS",
]

SENSITIVE_COLUMNS = {
    "CUSTOMER_EMAIL": "pii",
    "CUSTOMER_PHONE": "pii",
    "NATIONAL_ID": "pii",
    "DATE_OF_BIRTH": "pii",
    "SALARY_AMOUNT": "sensitive",
    "ACCOUNT_NUMBER": "pii",
    "HOME_ADDRESS": "pii",
}

COMMON_COLUMNS = [
    ("ID", "NUMBER"),
    ("CREATED_AT", "TIMESTAMP_NTZ"),
    ("UPDATED_AT", "TIMESTAMP_NTZ"),
    ("STATUS", "VARCHAR"),
    ("AMOUNT", "NUMBER"),
    ("CURRENCY", "VARCHAR"),
    ("REGION", "VARCHAR"),
    ("CHANNEL", "VARCHAR"),
    ("SOURCE_SYSTEM", "VARCHAR"),
]

OWNERS = [
    "sarah.chen@northwind.example",
    "dmitri.novak@northwind.example",
    "amara.okafor@northwind.example",
    "lars.eriksen@northwind.example",
    "priya.raman@northwind.example",
]

GLOSSARY_TERMS = ["Net Revenue", "Active Customer", "Exposure at Default", "Order Value", "Churn Risk"]


class DemoConnector(Connector):
    key = "demo"
    platform = "snowflake"
    display_name = "Demo estate (synthetic, deterministic)"
    query_catalog: dict[str, str] = {}

    def capabilities(self) -> set[str]:
        return {
            "datasets", "columns", "descriptions", "classification", "policies", "lineage",
            "column_lineage", "grants", "usage", "dq_monitors", "dq_incidents", "ml_assets",
            "semantic_models", "kpi_definitions", "agents", "rag_corpora", "governance_program",
            "audit_config",
        }

    def permission_manifest(self) -> PermissionManifest:
        return PermissionManifest(
            connector_key=self.key,
            principal="none -- synthetic data, no customer system is contacted",
            grants=(
                PermissionGrant(
                    scope="none",
                    grant="n/a",
                    purpose="Demo connector generates a synthetic estate locally",
                ),
            ),
            reads_row_data=False,
            notes="Every value is generated. No network call is made and no credential is read.",
        )

    def harvest(self) -> HarvestBundle:
        rng = random.Random(self.config.get("seed", SEED))
        anchor = HARVEST_ANCHOR
        bundle = HarvestBundle(connector_key=self.key, platform=self.platform)
        bundle.capabilities = self.capabilities()
        bundle.warnings = ["synthetic estate -- for demonstration and regression testing only"]

        datasets = self._build_datasets(rng, anchor)
        bundle.datasets = datasets
        self._attach_policies(rng, datasets, bundle)
        bundle.lineage = self._build_lineage(rng, datasets)
        bundle.usage = self._build_usage(rng, datasets, anchor)
        bundle.grants = self._build_grants(rng, datasets)
        monitors, incidents = self._build_dq(rng, datasets, anchor)
        bundle.dq_monitors = monitors
        bundle.dq_incidents = incidents
        bundle.ml_assets = self._build_ml_assets(rng)
        bundle.semantic_models, bundle.kpi_definitions = self._build_semantics(rng)
        bundle.agents = self._build_agents()
        bundle.rag_corpora = self._build_rag()
        bundle.governance_programs = self._build_governance(anchor)
        return bundle

    # -- estate ------------------------------------------------------------- #

    def _build_datasets(self, rng: random.Random, anchor: datetime) -> list[Dataset]:
        datasets: list[Dataset] = []
        for schema, (domain, base_tier) in DOMAINS.items():
            table_count = {1: 12, 2: 9, 3: 14}[base_tier]
            for index in range(table_count):
                stem = TABLE_STEMS[(index + len(schema)) % len(TABLE_STEMS)]
                name = stem if index < len(TABLE_STEMS) else f"{stem}_{index}"
                name = f"{name}_{index}" if index >= len(TABLE_STEMS) else name
                urn = f"snowflake://ANALYTICS.{schema}.{name}"
                if any(d.urn == urn for d in datasets):
                    urn = f"{urn}_{index}"
                tier = base_tier if index < table_count - 3 else min(3, base_tier + 1)
                certified = tier == 1 and rng.random() < 0.55
                described = rng.random() < (0.72 if tier == 1 else 0.38)
                has_owner = rng.random() < (0.78 if tier == 1 else 0.42)
                owner_verified = has_owner and rng.random() < 0.62
                last_queried = (
                    anchor - timedelta(days=rng.randint(0, 20))
                    if rng.random() < (0.95 if tier <= 2 else 0.55)
                    else anchor - timedelta(days=rng.randint(120, 500))
                )
                dataset = Dataset(
                    urn=urn,
                    platform="snowflake",
                    catalog="ANALYTICS",
                    schema_name=schema,
                    name=name,
                    object_type="TABLE",
                    domain=domain,
                    tier=tier,
                    description=(
                        f"{domain.title()} {stem.replace('_', ' ').lower()} at transaction grain, "
                        "refreshed hourly from the source system."
                        if described
                        else None
                    ),
                    owner=rng.choice(OWNERS) if has_owner else None,
                    owner_verified_at=anchor - timedelta(days=rng.randint(10, 300)) if owner_verified else None,
                    certified=certified,
                    governed=not (schema == "STAGING" and rng.random() < 0.5),
                    catalog_curated=rng.random() < (0.66 if tier == 1 else 0.3),
                    glossary_terms=[rng.choice(GLOSSARY_TERMS)] if tier == 1 and rng.random() < 0.5 else [],
                    bytes=rng.randint(50, 900) * 1_000_000,
                    last_queried_at=last_queried,
                )
                dataset.columns = self._build_columns(rng, dataset)
                datasets.append(dataset)
        return datasets

    def _build_columns(self, rng: random.Random, dataset: Dataset) -> list[Column]:
        columns: list[Column] = []
        description_rate = 0.68 if dataset.tier == 1 else (0.34 if dataset.tier == 2 else 0.12)
        for ordinal, (name, data_type) in enumerate(COMMON_COLUMNS, start=1):
            columns.append(
                Column(
                    name=name,
                    data_type=data_type,
                    ordinal=ordinal,
                    description=(
                        f"{name.replace('_', ' ').title()} for the {dataset.name.lower()} record."
                        if rng.random() < description_rate
                        else None
                    ),
                    glossary_term=(
                        rng.choice(GLOSSARY_TERMS)
                        if dataset.tier == 1 and name == "AMOUNT" and rng.random() < 0.6
                        else None
                    ),
                )
            )
        # Sensitive columns land mostly in customer-facing and HR domains.
        if dataset.domain in {"customer", "sales", "hr", "finance"}:
            for offset, (name, classification) in enumerate(SENSITIVE_COLUMNS.items()):
                if rng.random() > 0.45:
                    continue
                # Classification is present on most, protection on rather fewer --
                # the unfinished-rollout shape the Security hard blocker exists for.
                classified = rng.random() < 0.82
                catalog_classified = classified or rng.random() < 0.25
                columns.append(
                    Column(
                        name=name,
                        data_type="VARCHAR",
                        ordinal=len(COMMON_COLUMNS) + offset + 1,
                        description=None if rng.random() < 0.6 else f"{name.replace('_', ' ').title()}.",
                        platform_classification=classification if classified else None,
                        catalog_classification=classification if catalog_classified else None,
                    )
                )
        return columns

    def _attach_policies(self, rng: random.Random, datasets: list[Dataset], bundle: HarvestBundle) -> None:
        tag_bound = Policy(
            platform="snowflake",
            policy_type="masking",
            name="PII_MASK",
            bound_to_tag="PII",
            target_urns=[],
        )
        bundle.policies.append(tag_bound)
        for dataset in datasets:
            for column in dataset.columns:
                if not column.platform_classification:
                    continue
                # Tier-1 protection rollout is well advanced; Tier-2/3 lags badly.
                protection_rate = 0.86 if dataset.tier == 1 else 0.34
                if rng.random() < protection_rate:
                    column.protected = True
                    column.protection_kind = "masking_policy"
                    tag_bound.target_urns.append(f"{dataset.urn}.{column.name}")

    def _build_lineage(self, rng: random.Random, datasets: list[Dataset]) -> list[LineageEdge]:
        edges: list[LineageEdge] = []
        staging = [d for d in datasets if d.schema_name in {"STAGING", "OPERATIONS"}]
        consumers = [d for d in datasets if d.schema_name not in {"STAGING"}]
        if not staging:
            return edges
        for dataset in consumers:
            if rng.random() > (0.88 if dataset.tier == 1 else 0.55):
                continue
            upstream = rng.choice(staging)
            edges.append(
                LineageEdge(
                    upstream_urn=upstream.urn,
                    downstream_urn=dataset.urn,
                    level="table",
                    source="object_dependencies",
                    confidence=1.0,
                )
            )
            # Column edges are derived from ACCESS_HISTORY, so they are marked
            # inferred and the check library discounts their confidence.
            covered = rng.random() < (0.62 if dataset.tier == 1 else 0.2)
            if not covered:
                continue
            for column in dataset.columns:
                if rng.random() > 0.85:
                    continue
                source_column = next(
                    (c for c in upstream.columns if c.name == column.name), None
                )
                edges.append(
                    LineageEdge(
                        upstream_urn=upstream.urn,
                        downstream_urn=dataset.urn,
                        level="column",
                        upstream_column=source_column.name if source_column else column.name,
                        downstream_column=column.name,
                        source="access_history",
                        confidence=0.7,
                    )
                )
        return edges

    def _build_usage(self, rng: random.Random, datasets: list[Dataset], anchor: datetime) -> list[UsageEvent]:
        usage: list[UsageEvent] = []
        for dataset in datasets:
            if dataset.last_queried_at is None or dataset.last_queried_at < anchor - timedelta(days=90):
                continue
            for days_ago in (1, 7, 21):
                usage.append(
                    UsageEvent(
                        dataset_urn=dataset.urn,
                        event_date=anchor - timedelta(days=days_ago),
                        query_count=rng.randint(5, 400) if dataset.tier == 1 else rng.randint(1, 60),
                        distinct_users=rng.randint(1, 25),
                        identity_kind="service" if rng.random() < 0.35 else "human",
                    )
                )
        return usage

    def _build_grants(self, rng: random.Random, datasets: list[Dataset]) -> list[Grant]:
        grants: list[Grant] = []
        functional_roles = ["ANALYST_RO", "ENGINEER_RW", "RISK_RO", "FINANCE_RO", "MARKETING_RO"]
        for role in functional_roles:
            for dataset in rng.sample(datasets, k=min(18, len(datasets))):
                grants.append(
                    Grant(
                        platform="snowflake",
                        grantee=role,
                        grantee_type="role",
                        privilege="SELECT",
                        object_urn=dataset.urn,
                    )
                )
        # Direct-to-user grants: the hygiene problem GV/SE checks surface.
        for index in range(14):
            grants.append(
                Grant(
                    platform="snowflake",
                    grantee=f"user{index}@northwind.example",
                    grantee_type="user",
                    privilege="SELECT",
                    object_urn=rng.choice(datasets).urn,
                )
            )
        for holder in ("platform.admin@northwind.example", "legacy.etl@northwind.example", "ACCOUNTADMIN"):
            grants.append(
                Grant(
                    platform="snowflake",
                    grantee=holder,
                    grantee_type="user" if "@" in holder else "role",
                    privilege="ROLE ACCOUNTADMIN",
                    object_urn=None,
                    is_admin_role=True,
                )
            )
        return grants

    def _build_dq(
        self, rng: random.Random, datasets: list[Dataset], anchor: datetime
    ) -> tuple[list[DQMonitor], list[DQIncident]]:
        monitors: list[DQMonitor] = []
        incidents: list[DQIncident] = []
        for dataset in datasets:
            if dataset.tier == 1:
                types = ["completeness", "freshness"]
                if rng.random() < 0.55:
                    types.append("validity")
            elif dataset.tier == 2 and rng.random() < 0.5:
                types = ["freshness"]
            else:
                continue
            for check_type in types:
                monitors.append(
                    DQMonitor(
                        dataset_urn=dataset.urn,
                        tool="monte_carlo" if rng.random() < 0.6 else "snowflake_dmf",
                        check_type=check_type,
                        defined_as_data=rng.random() < 0.72,
                        enabled=True,
                        last_run_at=anchor - timedelta(hours=rng.randint(1, 30)),
                        pass_rate=round(rng.uniform(0.82, 1.0), 3),
                    )
                )
        tier1 = [d for d in datasets if d.tier == 1]
        for index in range(18):
            dataset = tier1[index % len(tier1)]
            opened = anchor - timedelta(days=rng.randint(3, 80))
            detected_by_monitor = rng.random() < 0.62
            resolved = rng.random() < 0.78
            incidents.append(
                DQIncident(
                    dataset_urn=dataset.urn,
                    tool="monte_carlo",
                    severity=rng.choice(["low", "medium", "high"]),
                    opened_at=opened,
                    detected_at=opened if detected_by_monitor else None,
                    consumer_reported_at=None if detected_by_monitor else opened + timedelta(hours=6),
                    resolved_at=opened + timedelta(days=rng.uniform(0.4, 6.0)) if resolved else None,
                    owner=rng.choice(OWNERS) if rng.random() < 0.7 else None,
                    false_positive=rng.random() < 0.18,
                )
            )
        return monitors, incidents

    def _build_ml_assets(self, rng: random.Random) -> list[MLAsset]:
        assets: list[MLAsset] = []
        model_names = ["churn_propensity", "fraud_score", "credit_limit", "next_best_action", "ltv_forecast"]
        for name in model_names:
            tracked = rng.random() < 0.7
            assets.append(
                MLAsset(
                    platform="snowflake",
                    kind="model",
                    name=name,
                    registered=rng.random() < 0.8,
                    training_data_lineage=rng.random() < 0.55,
                    promotion_gated=rng.random() < 0.5,
                    attributes={"experiment": tracked},
                )
            )
            if tracked:
                assets.append(
                    MLAsset(platform="snowflake", kind="experiment", name=f"exp_{name}", attributes={"model": name})
                )
        for name, external in (
            ("fraud_score_serving", False),
            ("churn_serving", False),
            ("support_copilot_llm", True),
            ("doc_summariser_llm", True),
        ):
            assets.append(
                MLAsset(
                    platform="snowflake",
                    kind="endpoint",
                    name=name,
                    registered=not external and rng.random() < 0.85,
                    training_data_lineage=not external,
                    promotion_gated=rng.random() < 0.45,
                    gateway_governed=external and rng.random() < 0.4,
                    attributes={"external": external},
                )
            )
        for index, name in enumerate(["customer_features", "transaction_features", "risk_features"]):
            assets.append(
                MLAsset(
                    platform="snowflake",
                    kind="feature_table",
                    name=name,
                    consumers=2 if index == 0 else 1,
                )
            )
        return assets

    def _build_semantics(self, rng: random.Random) -> tuple[list[SemanticModel], list[KPIDefinition]]:
        models = [
            SemanticModel(
                platform="snowflake",
                name="sales_semantic_view",
                certified=True,
                field_count=48,
                described_field_count=41,
                synonym_field_count=22,
                report_views=8200,
                covered_domains=["sales", "customer"],
                nl_answer_acceptance=0.71,
            ),
            SemanticModel(
                platform="powerbi",
                name="finance_exec_model",
                certified=True,
                field_count=63,
                described_field_count=39,
                synonym_field_count=11,
                report_views=6100,
                covered_domains=["finance"],
                nl_answer_acceptance=0.58,
            ),
            SemanticModel(
                platform="powerbi",
                name="marketing_adhoc_model",
                certified=False,
                field_count=57,
                described_field_count=18,
                synonym_field_count=4,
                report_views=4300,
                covered_domains=["marketing"],
            ),
            SemanticModel(
                platform="powerbi",
                name="risk_shadow_model",
                certified=False,
                field_count=39,
                described_field_count=12,
                synonym_field_count=2,
                report_views=2600,
                covered_domains=["risk"],
            ),
        ]
        kpis: list[KPIDefinition] = []
        definitions = {
            "Net Revenue": [("sales_semantic_view", "h_net_rev_1", True), ("finance_exec_model", "h_net_rev_2", True)],
            "Active Customer": [
                ("sales_semantic_view", "h_active_1", True),
                ("marketing_adhoc_model", "h_active_2", False),
                ("risk_shadow_model", "h_active_3", False),
            ],
            "Order Value": [("sales_semantic_view", "h_order_1", True)],
            "Exposure at Default": [("risk_shadow_model", "h_ead_1", False)],
            "Churn Risk": [("marketing_adhoc_model", "h_churn_1", False)],
        }
        for kpi_name, entries in definitions.items():
            for model_name, expression_hash, certified in entries:
                kpis.append(
                    KPIDefinition(
                        kpi_name=kpi_name,
                        semantic_model=model_name,
                        expression_hash=expression_hash,
                        certified=certified,
                    )
                )
        return models, kpis

    def _build_agents(self) -> list[AgentAsset]:
        return [
            AgentAsset(
                name="finance-analyst-copilot",
                identity_kind="shared",
                scoped_roles=False,
                write_actions=False,
                write_approval_gate=False,
                action_audit=True,
                replayable_trail=False,
                entitlement_reconciliation=False,
                inference_control_policy=False,
                tools=["semantic_query", "document_search"],
                runtime_trust_signals=False,
            ),
            AgentAsset(
                name="ops-remediation-agent",
                identity_kind="distinct",
                scoped_roles=True,
                write_actions=True,
                write_approval_gate=True,
                action_audit=True,
                replayable_trail=True,
                entitlement_reconciliation=False,
                inference_control_policy=False,
                tools=["ticketing", "warehouse_query", "runbook_exec"],
                runtime_trust_signals=True,
            ),
            AgentAsset(
                name="customer-support-assistant",
                identity_kind="shared",
                scoped_roles=False,
                write_actions=True,
                write_approval_gate=False,
                action_audit=False,
                replayable_trail=False,
                entitlement_reconciliation=False,
                inference_control_policy=False,
                tools=["crm_lookup", "document_search", "email_draft"],
                runtime_trust_signals=False,
            ),
        ]

    def _build_rag(self) -> list[RAGCorpus]:
        return [
            RAGCorpus(
                name="policies-and-procedures",
                source_system="sharepoint",
                authoritative_doc_count=4200,
                indexed_doc_count=3100,
                stale_doc_count=380,
                duplicate_doc_count=210,
                docs_with_owner=2600,
                docs_with_date=3000,
                docs_with_classification=1400,
                docs_with_audience=900,
                structured_doc_count=2100,
                scanned_doc_count=420,
                table_heavy_doc_count=580,
                vector_store="snowflake_cortex_search",
                embedding_refresh_hours=168.0,
                content_change_hours=72.0,
                contains_classified=True,
                acl_propagated=False,
                retrieval_filter_enforced=False,
                eval_set_present=True,
                citation_enforced=True,
                hallucination_monitoring=False,
            ),
            RAGCorpus(
                name="product-knowledge-base",
                source_system="confluence",
                authoritative_doc_count=1800,
                indexed_doc_count=1750,
                stale_doc_count=90,
                duplicate_doc_count=40,
                docs_with_owner=1600,
                docs_with_date=1740,
                docs_with_classification=1500,
                docs_with_audience=1450,
                structured_doc_count=1600,
                scanned_doc_count=20,
                table_heavy_doc_count=130,
                vector_store="snowflake_cortex_search",
                embedding_refresh_hours=24.0,
                content_change_hours=48.0,
                contains_classified=False,
                acl_propagated=True,
                retrieval_filter_enforced=True,
                eval_set_present=True,
                citation_enforced=True,
                hallucination_monitoring=True,
            ),
        ]

    def _build_governance(self, anchor: datetime) -> list[GovernanceProgram]:
        return [
            GovernanceProgram(
                tool="collibra",
                certifications_opened=180,
                certifications_completed=97,
                median_steward_response_hours=96.0,
                glossary_terms=420,
                glossary_terms_linked=188,
                access_reviews_current=True,
                audit_retention_days=365,
                audit_logging_enabled=True,
                last_scan_at=anchor - timedelta(days=2),
            ),
            GovernanceProgram(
                tool="snowflake_account",
                certifications_opened=0,
                certifications_completed=0,
                median_steward_response_hours=None,
                glossary_terms=0,
                glossary_terms_linked=0,
                access_reviews_current=False,
                audit_retention_days=180,
                audit_logging_enabled=True,
                last_scan_at=anchor,
            ),
        ]
