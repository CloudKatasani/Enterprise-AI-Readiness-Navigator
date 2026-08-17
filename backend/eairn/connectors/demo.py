"""Demo connector: deterministic synthetic estates.

Used for demonstrations, for the seeded Portal, and as the fixture behind the
golden scoring tests. Deterministic by construction -- a fixed seed and a fixed
iteration order -- so the same configuration always produces the same evidence,
the same scores and the same snapshot hash.

Two configuration axes shape the estate (see ``profiles.py``): the **industry**
decides domains, platform, table naming and where sensitive data concentrates;
the **maturity** profile decides the coverage rates a governance programme has
actually achieved. Neither sets a score -- they set estate facts, and the check
library measures whatever those facts support.

    build_connector("demo", {"industry": "utilities", "maturity": "at_risk"})
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from eairn.connectors.base import Connector, HarvestBundle, PermissionGrant, PermissionManifest
from eairn.connectors.profiles import (
    INDUSTRY_PROFILES,
    MATURITY_PROFILES,
    PLATFORM_BY_INDUSTRY,
    IndustryProfile,
    MaturityProfile,
)
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

SENSITIVE_COLUMNS = {
    "CUSTOMER_EMAIL": "pii",
    "CUSTOMER_PHONE": "pii",
    "NATIONAL_ID": "pii",
    "DATE_OF_BIRTH": "pii",
    "HOME_ADDRESS": "pii",
    "ACCOUNT_NUMBER": "pii",
    "SALARY_AMOUNT": "sensitive",
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
    "sarah.chen",
    "dmitri.novak",
    "amara.okafor",
    "lars.eriksen",
    "priya.raman",
]

GOVERNANCE_TOOL_BY_PLATFORM = {
    "snowflake": "collibra",
    "databricks": "alation",
    "fabric": "purview",
    "bigquery": "atlan",
    "oracle": "informatica_cdgc",
}


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

    # -- configuration ------------------------------------------------------ #

    @property
    def industry(self) -> IndustryProfile:
        key = self.config.get("industry", "financial_services")
        if key not in INDUSTRY_PROFILES:
            raise ValueError(
                f"unknown industry profile {key!r}; available: {', '.join(sorted(INDUSTRY_PROFILES))}"
            )
        return INDUSTRY_PROFILES[key]

    @property
    def maturity(self) -> MaturityProfile:
        key = self.config.get("maturity", "emerging")
        if key not in MATURITY_PROFILES:
            raise ValueError(
                f"unknown maturity profile {key!r}; available: {', '.join(sorted(MATURITY_PROFILES))}"
            )
        return MATURITY_PROFILES[key]

    @property
    def estate_platform(self) -> str:
        return self.config.get("platform") or PLATFORM_BY_INDUSTRY.get(self.industry.key, "snowflake")

    @property
    def email_domain(self) -> str:
        return self.config.get("email_domain", "example.com")

    def harvest(self) -> HarvestBundle:
        industry, maturity = self.industry, self.maturity
        rng = random.Random(self.config.get("seed", SEED))
        anchor = HARVEST_ANCHOR
        platform = self.estate_platform

        bundle = HarvestBundle(connector_key=self.key, platform=platform)
        bundle.capabilities = self.capabilities()
        bundle.warnings = [
            f"synthetic {industry.label} estate at '{maturity.key}' maturity -- "
            "for demonstration and regression testing only"
        ]

        datasets = self._build_datasets(rng, anchor, industry, maturity, platform)
        bundle.datasets = datasets
        self._attach_policies(rng, datasets, maturity, bundle, platform)
        bundle.lineage = self._build_lineage(rng, datasets, maturity)
        bundle.usage = self._build_usage(rng, datasets, anchor)
        bundle.grants = self._build_grants(rng, datasets, maturity, platform)
        monitors, incidents = self._build_dq(rng, datasets, anchor, maturity)
        bundle.dq_monitors = monitors
        bundle.dq_incidents = incidents
        bundle.ml_assets = self._build_ml_assets(rng, industry, maturity, platform)
        bundle.semantic_models, bundle.kpi_definitions = self._build_semantics(
            rng, industry, maturity, platform
        )
        bundle.agents = self._build_agents(industry, maturity)
        bundle.rag_corpora = self._build_rag(industry, maturity)
        bundle.governance_programs = self._build_governance(anchor, maturity, platform)
        return bundle

    # -- estate ------------------------------------------------------------- #

    def _urn(self, platform: str, schema: str, name: str) -> str:
        return f"{platform}://ANALYTICS.{schema}.{name}"

    def _build_datasets(
        self,
        rng: random.Random,
        anchor: datetime,
        industry: IndustryProfile,
        maturity: MaturityProfile,
        platform: str,
    ) -> list[Dataset]:
        datasets: list[Dataset] = []
        stems = industry.table_stems
        for schema, domain, base_tier in industry.domains:
            table_count = {1: 12, 2: 9, 3: 14}[base_tier]
            for index in range(table_count):
                stem = stems[(index + len(schema)) % len(stems)]
                name = stem if index < len(stems) else f"{stem}_{index}"
                urn = self._urn(platform, schema, name)
                if any(d.urn == urn for d in datasets):
                    urn = f"{urn}_{index}"
                tier = base_tier if index < table_count - 3 else min(3, base_tier + 1)
                described = rng.random() < (
                    maturity.table_description_rate if tier == 1 else maturity.table_description_rate * 0.6
                )
                has_owner = rng.random() < (
                    maturity.owner_rate if tier == 1 else maturity.owner_rate * 0.6
                )
                dataset = Dataset(
                    urn=urn,
                    platform=platform,
                    catalog="ANALYTICS",
                    schema_name=schema,
                    name=name,
                    object_type="TABLE",
                    domain=domain,
                    tier=tier,
                    description=(
                        f"{domain.replace('_', ' ').title()} {stem.replace('_', ' ').lower()} at "
                        "transaction grain, refreshed hourly from the source system."
                        if described
                        else None
                    ),
                    owner=(
                        f"{rng.choice(OWNERS)}@{self.email_domain}" if has_owner else None
                    ),
                    owner_verified_at=(
                        anchor - timedelta(days=rng.randint(10, 300))
                        if has_owner and rng.random() < maturity.owner_verified_rate
                        else None
                    ),
                    certified=tier == 1 and rng.random() < maturity.certification_rate,
                    governed=not (schema == "STAGING" and rng.random() < 0.5),
                    catalog_curated=rng.random()
                    < (maturity.curation_rate if tier == 1 else maturity.curation_rate * 0.5),
                    glossary_terms=(
                        [rng.choice(industry.kpi_names)]
                        if tier == 1 and rng.random() < maturity.glossary_rate
                        else []
                    ),
                    bytes=rng.randint(50, 900) * 1_000_000,
                    last_queried_at=(
                        anchor - timedelta(days=rng.randint(0, 20))
                        if rng.random() < (0.95 if tier <= 2 else 0.55)
                        else anchor - timedelta(days=rng.randint(120, 500))
                    ),
                )
                dataset.columns = self._build_columns(rng, dataset, industry, maturity)
                datasets.append(dataset)
        return datasets

    def _build_columns(
        self,
        rng: random.Random,
        dataset: Dataset,
        industry: IndustryProfile,
        maturity: MaturityProfile,
    ) -> list[Column]:
        columns: list[Column] = []
        description_rate = (
            maturity.tier1_description_rate
            if dataset.tier == 1
            else (maturity.tier2_description_rate if dataset.tier == 2 else maturity.tier2_description_rate * 0.4)
        )
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
                        rng.choice(industry.kpi_names)
                        if dataset.tier == 1 and name == "AMOUNT" and rng.random() < maturity.glossary_rate
                        else None
                    ),
                )
            )
        # Sensitive columns concentrate where the industry says they do.
        if dataset.domain in industry.sensitive_domains:
            for offset, (name, classification) in enumerate(SENSITIVE_COLUMNS.items()):
                if rng.random() > 0.45:
                    continue
                classified = rng.random() < maturity.classification_rate
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

    def _attach_policies(
        self,
        rng: random.Random,
        datasets: list[Dataset],
        maturity: MaturityProfile,
        bundle: HarvestBundle,
        platform: str,
    ) -> None:
        tag_bound = Policy(
            platform=platform,
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
                protection_rate = (
                    maturity.tier1_protection_rate if dataset.tier == 1 else maturity.other_protection_rate
                )
                if rng.random() < protection_rate:
                    column.protected = True
                    column.protection_kind = "masking_policy"
                    tag_bound.target_urns.append(f"{dataset.urn}.{column.name}")

    def _build_lineage(
        self, rng: random.Random, datasets: list[Dataset], maturity: MaturityProfile
    ) -> list[LineageEdge]:
        edges: list[LineageEdge] = []
        staging = [d for d in datasets if d.schema_name in {"STAGING", "OPERATIONS", "FIELD_OPS", "SUPPLY"}]
        if not staging:
            staging = [d for d in datasets if d.tier == 3]
        consumers = [d for d in datasets if d.schema_name != "STAGING"]
        if not staging:
            return edges
        for dataset in consumers:
            if rng.random() > (maturity.lineage_rate if dataset.tier == 1 else maturity.lineage_rate * 0.6):
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
            # Column edges derive from query history, so they are marked
            # inferred and the check library discounts their confidence.
            covered = rng.random() < (
                maturity.column_lineage_rate if dataset.tier == 1 else maturity.column_lineage_rate * 0.3
            )
            if not covered:
                continue
            for column in dataset.columns:
                if rng.random() > 0.85:
                    continue
                source_column = next((c for c in upstream.columns if c.name == column.name), None)
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

    def _build_usage(
        self, rng: random.Random, datasets: list[Dataset], anchor: datetime
    ) -> list[UsageEvent]:
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

    def _build_grants(
        self,
        rng: random.Random,
        datasets: list[Dataset],
        maturity: MaturityProfile,
        platform: str,
    ) -> list[Grant]:
        grants: list[Grant] = []
        functional_roles = ["ANALYST_RO", "ENGINEER_RW", "RISK_RO", "FINANCE_RO", "MARKETING_RO"]
        for role in functional_roles:
            for dataset in rng.sample(datasets, k=min(18, len(datasets))):
                grants.append(
                    Grant(
                        platform=platform,
                        grantee=role,
                        grantee_type="role",
                        privilege="SELECT",
                        object_urn=dataset.urn,
                    )
                )
        # Direct-to-user grants scale inversely with governance maturity.
        direct_count = int(round(30 * (1 - maturity.owner_verified_rate))) + 2
        for index in range(direct_count):
            grants.append(
                Grant(
                    platform=platform,
                    grantee=f"user{index}@{self.email_domain}",
                    grantee_type="user",
                    privilege="SELECT",
                    object_urn=rng.choice(datasets).urn,
                )
            )
        admin_holders = ["platform.admin", "legacy.etl"]
        if maturity.key in {"emerging", "at_risk"}:
            admin_holders += ["data.eng.lead", "bi.admin"]
        if maturity.key == "at_risk":
            admin_holders += ["contractor.ops", "analytics.lead", "release.bot"]
        for holder in admin_holders:
            grants.append(
                Grant(
                    platform=platform,
                    grantee=f"{holder}@{self.email_domain}",
                    grantee_type="user",
                    privilege="ROLE ACCOUNTADMIN",
                    object_urn=None,
                    is_admin_role=True,
                )
            )
        grants.append(
            Grant(
                platform=platform,
                grantee="ACCOUNTADMIN",
                grantee_type="role",
                privilege="ROLE ACCOUNTADMIN",
                object_urn=None,
                is_admin_role=True,
            )
        )
        return grants

    def _build_dq(
        self,
        rng: random.Random,
        datasets: list[Dataset],
        anchor: datetime,
        maturity: MaturityProfile,
    ) -> tuple[list[DQMonitor], list[DQIncident]]:
        monitors: list[DQMonitor] = []
        incidents: list[DQIncident] = []
        for dataset in datasets:
            if dataset.tier == 1:
                types = ["completeness", "freshness"]
                if rng.random() < maturity.monitor_validity_rate:
                    types.append("validity")
            elif dataset.tier == 2 and rng.random() < maturity.tier2_monitor_rate:
                types = ["freshness"]
            else:
                continue
            for check_type in types:
                monitors.append(
                    DQMonitor(
                        dataset_urn=dataset.urn,
                        tool="monte_carlo" if rng.random() < 0.6 else "platform_native",
                        check_type=check_type,
                        defined_as_data=rng.random() < maturity.rules_as_data_rate,
                        enabled=True,
                        last_run_at=anchor - timedelta(hours=rng.randint(1, 30)),
                        pass_rate=round(rng.uniform(maturity.monitor_pass_floor, 1.0), 3),
                    )
                )
        tier1 = [d for d in datasets if d.tier == 1]
        if not tier1:
            return monitors, incidents
        mttr_ceiling = {"leading": 1.4, "advancing": 3.0, "emerging": 6.0, "at_risk": 11.0}[maturity.key]
        for index in range(18):
            dataset = tier1[index % len(tier1)]
            opened = anchor - timedelta(days=rng.randint(3, 80))
            detected_by_monitor = rng.random() < maturity.incident_detected_rate
            resolved = rng.random() < maturity.incident_resolved_rate
            incidents.append(
                DQIncident(
                    dataset_urn=dataset.urn,
                    tool="monte_carlo",
                    severity=rng.choice(["low", "medium", "high"]),
                    opened_at=opened,
                    detected_at=opened if detected_by_monitor else None,
                    consumer_reported_at=None if detected_by_monitor else opened + timedelta(hours=6),
                    resolved_at=(
                        opened + timedelta(days=rng.uniform(0.3, mttr_ceiling)) if resolved else None
                    ),
                    owner=(
                        f"{rng.choice(OWNERS)}@{self.email_domain}"
                        if rng.random() < maturity.incident_owned_rate
                        else None
                    ),
                    false_positive=rng.random() < maturity.incident_false_positive_rate,
                )
            )
        return monitors, incidents

    def _build_ml_assets(
        self,
        rng: random.Random,
        industry: IndustryProfile,
        maturity: MaturityProfile,
        platform: str,
    ) -> list[MLAsset]:
        assets: list[MLAsset] = []
        for name in industry.model_names:
            tracked = rng.random() < (0.5 + maturity.model_registered_rate / 2)
            assets.append(
                MLAsset(
                    platform=platform,
                    kind="model",
                    name=name,
                    registered=rng.random() < maturity.model_registered_rate,
                    training_data_lineage=rng.random() < maturity.model_lineage_rate,
                    promotion_gated=rng.random() < maturity.promotion_gate_rate,
                    attributes={"experiment": tracked},
                )
            )
            if tracked:
                assets.append(
                    MLAsset(platform=platform, kind="experiment", name=f"exp_{name}", attributes={"model": name})
                )
        serving = [
            (f"{industry.model_names[0]}_serving", False),
            (f"{industry.model_names[1]}_serving", False),
            ("assistant_llm_endpoint", True),
            ("doc_summariser_llm", True),
        ]
        for name, external in serving:
            assets.append(
                MLAsset(
                    platform=platform,
                    kind="endpoint",
                    name=name,
                    registered=not external and rng.random() < maturity.model_registered_rate,
                    training_data_lineage=not external and rng.random() < maturity.model_lineage_rate,
                    promotion_gated=rng.random() < maturity.promotion_gate_rate,
                    gateway_governed=external and rng.random() < maturity.gateway_rate,
                    attributes={"external": external},
                )
            )
        feature_tables = ["customer_features", "transaction_features", "operational_features"]
        reuse_cut = {"leading": 3, "advancing": 2, "emerging": 1, "at_risk": 0}[maturity.key]
        for index, name in enumerate(feature_tables):
            assets.append(
                MLAsset(platform=platform, kind="feature_table", name=name, consumers=2 if index < reuse_cut else 1)
            )
        return assets

    def _build_semantics(
        self,
        rng: random.Random,
        industry: IndustryProfile,
        maturity: MaturityProfile,
        platform: str,
    ) -> tuple[list[SemanticModel], list[KPIDefinition]]:
        certified_share = {"leading": 4, "advancing": 3, "emerging": 2, "at_risk": 0}[maturity.key]
        model_specs = [
            ("core_semantic_view", platform, 48, 8200),
            ("finance_exec_model", "powerbi", 63, 6100),
            ("operations_adhoc_model", "powerbi", 57, 4300),
            ("shadow_reporting_model", "powerbi", 39, 2600),
        ]
        models: list[SemanticModel] = []
        for index, (name, model_platform, fields, views) in enumerate(model_specs):
            described = int(fields * min(1.0, maturity.tier1_description_rate + 0.05))
            synonyms = int(fields * maturity.glossary_rate)
            models.append(
                SemanticModel(
                    platform=model_platform,
                    name=name,
                    certified=index < certified_share,
                    field_count=fields,
                    described_field_count=described,
                    synonym_field_count=synonyms,
                    report_views=views,
                    covered_domains=[d[1] for d in industry.domains[: index + 2]],
                    nl_answer_acceptance=(
                        round(0.45 + 0.45 * maturity.glossary_linked_ratio, 3) if index < 2 else None
                    ),
                )
            )

        # Divergent KPI definitions are the semantic-layer failure that matters,
        # so their count tracks maturity directly.
        duplicates = {"leading": 0, "advancing": 1, "emerging": 2, "at_risk": 3}[maturity.key]
        kpis: list[KPIDefinition] = []
        for index, kpi_name in enumerate(industry.kpi_names):
            kpis.append(
                KPIDefinition(
                    kpi_name=kpi_name,
                    semantic_model=model_specs[0][0],
                    expression_hash=f"h_{index}_canonical",
                    certified=index < certified_share,
                )
            )
            if index < duplicates:
                kpis.append(
                    KPIDefinition(
                        kpi_name=kpi_name,
                        semantic_model=model_specs[(index % 3) + 1][0],
                        expression_hash=f"h_{index}_divergent",
                        certified=False,
                    )
                )
        return models, kpis

    def _build_agents(self, industry: IndustryProfile, maturity: MaturityProfile) -> list[AgentAsset]:
        distinct, scoped, gated, audited, replayable, reconciled, inference = maturity.agent_posture
        tool_sets = [
            ["semantic_query", "document_search"],
            ["ticketing", "warehouse_query", "runbook_exec"],
            ["crm_lookup", "document_search", "email_draft"],
        ]
        agents: list[AgentAsset] = []
        for index, name in enumerate(industry.agent_names):
            # The second agent is the write-capable one in every estate; its
            # approval gate is the difference between profiles.
            writes = index == 1 or (index == 2 and maturity.key in {"emerging", "at_risk"})
            agents.append(
                AgentAsset(
                    name=name,
                    identity_kind="distinct" if (distinct or index == 1) else "shared",
                    scoped_roles=scoped or (index == 1 and maturity.key == "emerging"),
                    write_actions=writes,
                    write_approval_gate=writes and (gated or index == 1) and maturity.key != "at_risk",
                    action_audit=audited,
                    replayable_trail=replayable or (index == 1 and maturity.key == "emerging"),
                    entitlement_reconciliation=reconciled,
                    inference_control_policy=inference,
                    tools=tool_sets[index % len(tool_sets)],
                    # The one well-governed agent consumes runtime trust signals
                    # even where the wider programme has not caught up.
                    runtime_trust_signals=(distinct and scoped)
                    or (index == 1 and maturity.key in {"advancing", "emerging"}),
                )
            )
        return agents

    def _build_rag(self, industry: IndustryProfile, maturity: MaturityProfile) -> list[RAGCorpus]:
        acl, filtered, eval_set, citations, hallucination = maturity.rag_posture
        corpora: list[RAGCorpus] = []
        for index, (name, source) in enumerate(industry.corpus_names):
            authoritative = 4200 if index == 0 else 1800
            indexed = int(authoritative * maturity.rag_index_coverage)
            metadata = int(indexed * maturity.rag_metadata_rate)
            # The first corpus is the regulated one: it holds classified content,
            # so its ACL posture is what the RAG hard blocker keys on.
            classified = index == 0
            corpora.append(
                RAGCorpus(
                    name=name,
                    source_system=source,
                    authoritative_doc_count=authoritative,
                    indexed_doc_count=indexed,
                    stale_doc_count=int(indexed * (1 - maturity.rag_index_coverage) * 0.8),
                    duplicate_doc_count=int(indexed * (1 - maturity.rag_metadata_rate) * 0.1),
                    docs_with_owner=metadata,
                    docs_with_date=int(indexed * min(1.0, maturity.rag_metadata_rate + 0.15)),
                    docs_with_classification=metadata,
                    docs_with_audience=int(indexed * max(0.0, maturity.rag_metadata_rate - 0.1)),
                    structured_doc_count=int(indexed * (0.6 + 0.3 * maturity.rag_metadata_rate)),
                    scanned_doc_count=int(indexed * (0.15 * (1 - maturity.rag_metadata_rate))),
                    table_heavy_doc_count=int(indexed * 0.12),
                    vector_store="managed_vector_index",
                    embedding_refresh_hours=maturity.rag_refresh_hours,
                    content_change_hours=72.0,
                    contains_classified=classified,
                    acl_propagated=acl or index > 0,
                    retrieval_filter_enforced=filtered or index > 0,
                    eval_set_present=eval_set,
                    citation_enforced=citations,
                    hallucination_monitoring=hallucination,
                )
            )
        return corpora

    def _build_governance(
        self, anchor: datetime, maturity: MaturityProfile, platform: str
    ) -> list[GovernanceProgram]:
        opened = 180
        terms = 420
        return [
            GovernanceProgram(
                tool=GOVERNANCE_TOOL_BY_PLATFORM.get(platform, "collibra"),
                certifications_opened=opened,
                certifications_completed=int(opened * maturity.certifications_completed_ratio),
                median_steward_response_hours=maturity.steward_response_hours,
                glossary_terms=terms,
                glossary_terms_linked=int(terms * maturity.glossary_linked_ratio),
                access_reviews_current=maturity.access_reviews_current,
                audit_retention_days=365 if maturity.key in {"leading", "advancing"} else 180,
                audit_logging_enabled=True,
                last_scan_at=anchor - timedelta(days=2),
            ),
            GovernanceProgram(
                tool=f"{platform}_account",
                certifications_opened=0,
                certifications_completed=0,
                median_steward_response_hours=None,
                glossary_terms=0,
                glossary_terms_linked=0,
                access_reviews_current=maturity.access_reviews_current,
                audit_retention_days=365 if maturity.key == "leading" else 180,
                audit_logging_enabled=maturity.key != "at_risk",
                last_scan_at=anchor,
            ),
        ]
