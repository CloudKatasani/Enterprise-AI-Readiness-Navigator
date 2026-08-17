"""EAIRN persistence model.

Three families of tables live here:

1. **Canonical metadata model** -- the platform-neutral shape every connector
   normalises into (Dataset, Column, LineageEdge, Policy, Tag, Owner, Usage
   Event, plus the AI/agent/RAG surfaces the readiness indices need). No row
   data ever lands here; only catalog-level metadata.
2. **Rubric-as-data** -- pillars, criteria, weights, grade bands, hard-blocker
   overrides and index dimensions, all versioned. Scoring logic reads these
   tables; nothing about a rubric is hardcoded in the engine.
3. **Evidence, scores and snapshots** -- immutable, keyed assessment runs that
   can be replayed byte-identically.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- #
# Tenancy & connections
# --------------------------------------------------------------------------- #


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(64), default="unspecified")
    size_band: Mapped[str] = mapped_column(String(32), default="unspecified")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    connections: Mapped[list["Connection"]] = relationship(back_populates="tenant")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="tenant")


class Connection(Base):
    """A configured, read-only connector instance for one platform or tool."""

    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    connector_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="connections")


class HarvestRun(Base):
    __tablename__ = "harvest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    connector_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------------------------------------------------------- #
# Canonical metadata model
# --------------------------------------------------------------------------- #


class Dataset(Base):
    """A table, view, model, file set or document collection."""

    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("tenant_id", "urn", name="uq_dataset_urn"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    harvest_run_id: Mapped[int | None] = mapped_column(ForeignKey("harvest_runs.id"), nullable=True)
    urn: Mapped[str] = mapped_column(String(512), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    catalog: Mapped[str | None] = mapped_column(String(128), nullable=True)
    schema_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(256))
    object_type: Mapped[str] = mapped_column(String(48), default="TABLE")
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tier: Mapped[int] = mapped_column(Integer, default=3)  # 1 = certified / crown jewel
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    certified: Mapped[bool] = mapped_column(Boolean, default=False)
    governed: Mapped[bool] = mapped_column(Boolean, default=True)  # e.g. UC vs hive_metastore
    catalog_curated: Mapped[bool] = mapped_column(Boolean, default=False)
    glossary_terms: Mapped[list] = mapped_column(JSON, default=list)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    last_queried_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)

    columns: Mapped[list["Column"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class Column(Base):
    __tablename__ = "columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(256))
    data_type: Mapped[str] = mapped_column(String(64), default="VARCHAR")
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sensitivity as declared by the *platform* (tags) and by the *catalog*.
    platform_classification: Mapped[str | None] = mapped_column(String(48), nullable=True)
    catalog_classification: Mapped[str | None] = mapped_column(String(48), nullable=True)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)  # masking / redaction / policy tag
    protection_kind: Mapped[str | None] = mapped_column(String(48), nullable=True)
    glossary_term: Mapped[str | None] = mapped_column(String(200), nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="columns")

    @property
    def is_sensitive(self) -> bool:
        return bool(self.platform_classification or self.catalog_classification)


class LineageEdge(Base):
    __tablename__ = "lineage_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    upstream_urn: Mapped[str] = mapped_column(String(512), index=True)
    downstream_urn: Mapped[str] = mapped_column(String(512), index=True)
    level: Mapped[str] = mapped_column(String(16), default="table")  # table | column
    upstream_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    downstream_column: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="platform")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class Policy(Base):
    """Masking policy, row access policy, redaction rule or policy tag."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    policy_type: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(256))
    bound_to_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_urns: Mapped[list] = mapped_column(JSON, default=list)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class Grant(Base):
    __tablename__ = "grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    grantee: Mapped[str] = mapped_column(String(200))
    grantee_type: Mapped[str] = mapped_column(String(32), default="role")  # role | user | service
    privilege: Mapped[str] = mapped_column(String(64))
    object_urn: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_admin_role: Mapped[bool] = mapped_column(Boolean, default=False)


class UsageEvent(Base):
    """Daily rollup of query activity -- never individual statements."""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dataset_urn: Mapped[str] = mapped_column(String(512), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    distinct_users: Mapped[int] = mapped_column(Integer, default=0)
    identity_kind: Mapped[str] = mapped_column(String(32), default="human")  # human | service | agent


class DQMonitor(Base):
    __tablename__ = "dq_monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dataset_urn: Mapped[str] = mapped_column(String(512), index=True)
    tool: Mapped[str] = mapped_column(String(48))
    check_type: Mapped[str] = mapped_column(String(32))  # completeness | freshness | validity | anomaly
    defined_as_data: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pass_rate: Mapped[float] = mapped_column(Float, default=1.0)


class DQIncident(Base):
    __tablename__ = "dq_incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dataset_urn: Mapped[str] = mapped_column(String(512))
    tool: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumer_reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    false_positive: Mapped[bool] = mapped_column(Boolean, default=False)


class MLAsset(Base):
    __tablename__ = "ml_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))  # experiment | model | endpoint | feature_table
    name: Mapped[str] = mapped_column(String(256))
    registered: Mapped[bool] = mapped_column(Boolean, default=False)
    training_data_lineage: Mapped[bool] = mapped_column(Boolean, default=False)
    promotion_gated: Mapped[bool] = mapped_column(Boolean, default=False)
    gateway_governed: Mapped[bool] = mapped_column(Boolean, default=False)
    consumers: Mapped[int] = mapped_column(Integer, default=0)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)


class SemanticModel(Base):
    __tablename__ = "semantic_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(256))
    certified: Mapped[bool] = mapped_column(Boolean, default=False)
    field_count: Mapped[int] = mapped_column(Integer, default=0)
    described_field_count: Mapped[int] = mapped_column(Integer, default=0)
    synonym_field_count: Mapped[int] = mapped_column(Integer, default=0)
    report_views: Mapped[int] = mapped_column(Integer, default=0)
    covered_domains: Mapped[list] = mapped_column(JSON, default=list)
    nl_answer_acceptance: Mapped[float | None] = mapped_column(Float, nullable=True)


class KPIDefinition(Base):
    """One physical definition of a KPI. >1 row per KPI name = duplication."""

    __tablename__ = "kpi_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    kpi_name: Mapped[str] = mapped_column(String(200), index=True)
    semantic_model: Mapped[str] = mapped_column(String(256))
    expression_hash: Mapped[str] = mapped_column(String(64))
    certified: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentAsset(Base):
    """A deployed agent or copilot, plus the safety posture around it."""

    __tablename__ = "agent_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    identity_kind: Mapped[str] = mapped_column(String(32), default="shared")  # distinct | shared | human
    scoped_roles: Mapped[bool] = mapped_column(Boolean, default=False)
    write_actions: Mapped[bool] = mapped_column(Boolean, default=False)
    write_approval_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    action_audit: Mapped[bool] = mapped_column(Boolean, default=False)
    replayable_trail: Mapped[bool] = mapped_column(Boolean, default=False)
    entitlement_reconciliation: Mapped[bool] = mapped_column(Boolean, default=False)
    inference_control_policy: Mapped[bool] = mapped_column(Boolean, default=False)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    runtime_trust_signals: Mapped[bool] = mapped_column(Boolean, default=False)


class RAGCorpus(Base):
    __tablename__ = "rag_corpora"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_system: Mapped[str] = mapped_column(String(64))
    authoritative_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    stale_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    docs_with_owner: Mapped[int] = mapped_column(Integer, default=0)
    docs_with_date: Mapped[int] = mapped_column(Integer, default=0)
    docs_with_classification: Mapped[int] = mapped_column(Integer, default=0)
    docs_with_audience: Mapped[int] = mapped_column(Integer, default=0)
    structured_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    scanned_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    table_heavy_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_store: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_refresh_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_change_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    contains_classified: Mapped[bool] = mapped_column(Boolean, default=False)
    acl_propagated: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieval_filter_enforced: Mapped[bool] = mapped_column(Boolean, default=False)
    eval_set_present: Mapped[bool] = mapped_column(Boolean, default=False)
    citation_enforced: Mapped[bool] = mapped_column(Boolean, default=False)
    hallucination_monitoring: Mapped[bool] = mapped_column(Boolean, default=False)


class GovernanceProgram(Base):
    """Operational liveness of the governance/catalog program itself."""

    __tablename__ = "governance_programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(48))
    certifications_opened: Mapped[int] = mapped_column(Integer, default=0)
    certifications_completed: Mapped[int] = mapped_column(Integer, default=0)
    median_steward_response_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    glossary_terms: Mapped[int] = mapped_column(Integer, default=0)
    glossary_terms_linked: Mapped[int] = mapped_column(Integer, default=0)
    access_reviews_current: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_retention_days: Mapped[int] = mapped_column(Integer, default=0)
    audit_logging_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuestionnaireResponse(Base):
    """Supplementary self-reported evidence, cross-validated against machine evidence."""

    __tablename__ = "questionnaire_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    numeric_answer: Mapped[float | None] = mapped_column(Float, nullable=True)
    respondent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SamplingAuthorization(Base):
    """Explicit, logged, per-dataset authorization for optional row sampling."""

    __tablename__ = "sampling_authorizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    dataset_urn: Mapped[str] = mapped_column(String(512))
    authorized_by: Mapped[str] = mapped_column(String(200))
    authorized_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    justification: Mapped[str] = mapped_column(Text)


# --------------------------------------------------------------------------- #
# Rubric as data
# --------------------------------------------------------------------------- #


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.80)
    source_digest: Mapped[str] = mapped_column(String(64), default="")
    #: Display names for the overlay indices, e.g. {"ARI": "Agent Readiness Index"}.
    #: Held as rubric data so a fork can rename an index without touching code.
    index_names: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    pillars: Mapped[list["RubricPillar"]] = relationship(
        back_populates="rubric", cascade="all, delete-orphan"
    )
    bands: Mapped[list["RubricGradeBand"]] = relationship(
        back_populates="rubric", cascade="all, delete-orphan"
    )
    overrides: Mapped[list["RubricOverride"]] = relationship(
        back_populates="rubric", cascade="all, delete-orphan"
    )
    dimensions: Mapped[list["RubricIndexDimension"]] = relationship(
        back_populates="rubric", cascade="all, delete-orphan"
    )


class RubricPillar(Base):
    __tablename__ = "rubric_pillars"
    __table_args__ = (UniqueConstraint("rubric_id", "key", name="uq_pillar_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(120))
    core_question: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=0.0)  # 0 => overlay, not in composite
    scoring_mode: Mapped[str] = mapped_column(String(24), default="composite")  # composite | overlay
    rationale: Mapped[str] = mapped_column(Text, default="")

    rubric: Mapped[Rubric] = relationship(back_populates="pillars")
    criteria: Mapped[list["RubricCriterion"]] = relationship(
        back_populates="pillar", cascade="all, delete-orphan"
    )


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (UniqueConstraint("pillar_id", "key", name="uq_criterion_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pillar_id: Mapped[int] = mapped_column(ForeignKey("rubric_pillars.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    check_id: Mapped[str] = mapped_column(String(64), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")

    pillar: Mapped[RubricPillar] = relationship(back_populates="criteria")


class RubricGradeBand(Base):
    __tablename__ = "rubric_grade_bands"

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(24), default="composite")  # composite | ARI | RRI
    min_score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(48))
    interpretation: Mapped[str] = mapped_column(Text, default="")

    rubric: Mapped[Rubric] = relationship(back_populates="bands")


class RubricOverride(Base):
    """Hard-blocker cap: certain findings bound a score regardless of arithmetic."""

    __tablename__ = "rubric_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(64))
    check_id: Mapped[str] = mapped_column(String(64))
    condition: Mapped[str] = mapped_column(String(32))  # result_below | result_at_or_below | failing_targets_above
    threshold: Mapped[float] = mapped_column(Float)
    cap_scope: Mapped[str] = mapped_column(String(48))  # pillar key, "composite", "ARI" or "RRI"
    cap_value: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text, default="")

    rubric: Mapped[Rubric] = relationship(back_populates="overrides")


class RubricIndexDimension(Base):
    """A dimension of the ARI or RRI overlay index."""

    __tablename__ = "rubric_index_dimensions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rubric_id: Mapped[int] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    index_key: Mapped[str] = mapped_column(String(16))  # ARI | RRI
    key: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(120))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    description: Mapped[str] = mapped_column(Text, default="")
    check_ids: Mapped[list] = mapped_column(JSON, default=list)

    rubric: Mapped[Rubric] = relationship(back_populates="dimensions")


# --------------------------------------------------------------------------- #
# Assessment: evidence, scores, snapshot
# --------------------------------------------------------------------------- #


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rubric_version: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(32), default="running")  # running | complete | failed
    harvested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(48), nullable=True)
    ari_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ari_grade: Mapped[str | None] = mapped_column(String(48), nullable=True)
    rri_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rri_grade: Mapped[str | None] = mapped_column(String(48), nullable=True)
    connectors: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    tenant: Mapped[Tenant] = relationship(back_populates="assessments")
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    scores: Mapped[list["Score"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class Evidence(Base):
    """{check_id, target, result, confidence, rationale} -- blueprint S13 rule 2."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    check_id: Mapped[str] = mapped_column(String(64), index=True)
    check_title: Mapped[str] = mapped_column(String(256), default="")
    pillar_key: Mapped[str] = mapped_column(String(48), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="cross-platform")
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_urn: Mapped[str] = mapped_column(String(512), default="estate")
    target_type: Mapped[str] = mapped_column(String(48), default="estate")
    result: Mapped[float] = mapped_column(Float)  # normalised 0-100
    measured: Mapped[dict] = mapped_column(JSON, default=dict)  # raw numerator/denominator etc.
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(24), default="info")
    status: Mapped[str] = mapped_column(String(32), default="accepted")  # accepted | pending_review | rejected
    failing_targets: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    assessment: Mapped[Assessment] = relationship(back_populates="evidence")


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(32))  # criterion | pillar | composite | index | index_dimension
    key: Mapped[str] = mapped_column(String(64), index=True)
    parent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    score: Mapped[float] = mapped_column(Float)
    raw_score: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    grade: Mapped[str | None] = mapped_column(String(48), nullable=True)
    capped_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)

    assessment: Mapped[Assessment] = relationship(back_populates="scores")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    playbook_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    pillar_key: Mapped[str] = mapped_column(String(48))
    horizon: Mapped[str] = mapped_column(String(32))  # quick_win | structural | strategic
    summary: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    effort_days: Mapped[float] = mapped_column(Float, default=0.0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    projected_criterion_score: Mapped[float] = mapped_column(Float, default=0.0)
    composite_impact: Mapped[float] = mapped_column(Float, default=0.0)
    unblocks: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    generator: Mapped[str] = mapped_column(String(32), default="playbook")  # playbook | llm
    llm_prompt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft | approved | rejected
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdvisorNarrative(Base):
    """Executive narrative drafted by the AI Advisor, grounded in one snapshot."""

    __tablename__ = "advisor_narratives"

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(48), default="executive_summary")
    body: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)  # evidence IDs
    generator: Mapped[str] = mapped_column(String(32), default="template")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CohortStat(Base):
    """Anonymised peer-cohort percentile distribution for one metric."""

    __tablename__ = "cohort_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_key: Mapped[str] = mapped_column(String(120), index=True)
    industry: Mapped[str] = mapped_column(String(64))
    size_band: Mapped[str] = mapped_column(String(32))
    platform_mix: Mapped[str] = mapped_column(String(64), default="any")
    metric_scope: Mapped[str] = mapped_column(String(32), default="pillar")
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    n: Mapped[int] = mapped_column(Integer, default=0)
    p25: Mapped[float] = mapped_column(Float, default=0.0)
    p50: Mapped[float] = mapped_column(Float, default=0.0)
    p75: Mapped[float] = mapped_column(Float, default=0.0)
    p90: Mapped[float] = mapped_column(Float, default=0.0)
