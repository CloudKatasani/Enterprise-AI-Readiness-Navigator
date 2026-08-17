"""Assessment pipeline: connect -> harvest -> evaluate -> score -> recommend -> snapshot.

One run produces one immutable snapshot keyed by
``{tenant, snapshot_id, rubric_version, harvested_at}``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from eairn.checks import Estate, run_checks
from eairn.config import get_settings
from eairn.connectors import HarvestBundle, build_connector
from eairn.models import (
    AgentAsset,
    Assessment,
    Column,
    Dataset,
    DQIncident,
    DQMonitor,
    Evidence,
    GovernanceProgram,
    Grant,
    HarvestRun,
    KPIDefinition,
    LineageEdge,
    MLAsset,
    Policy,
    QuestionnaireResponse,
    RAGCorpus,
    Score,
    SemanticModel,
    Tenant,
    UsageEvent,
)
from eairn.recommend import generate_recommendations
from eairn.rubric import get_rubric, install_rubric
from eairn.scoring import persist_scores, score_assessment, snapshot_hash

_CANONICAL_TABLES = (
    LineageEdge, Policy, Grant, UsageEvent, DQMonitor, DQIncident, MLAsset,
    SemanticModel, KPIDefinition, AgentAsset, RAGCorpus, GovernanceProgram,
)


class PipelineError(RuntimeError):
    pass


def _wipe_canonical(session: Session, tenant_id: int) -> None:
    """A harvest replaces the tenant's canonical view; snapshots preserve history."""
    dataset_ids = session.scalars(select(Dataset.id).where(Dataset.tenant_id == tenant_id)).all()
    if dataset_ids:
        session.execute(delete(Column).where(Column.dataset_id.in_(dataset_ids)))
    session.execute(delete(Dataset).where(Dataset.tenant_id == tenant_id))
    for model in _CANONICAL_TABLES:
        session.execute(delete(model).where(model.tenant_id == tenant_id))
    session.flush()


def persist_bundle(session: Session, tenant: Tenant, run: HarvestRun, bundle: HarvestBundle) -> None:
    """Stamp tenant/run identity onto canonical entities and persist them."""
    for dataset in bundle.datasets:
        dataset.tenant_id = tenant.id
        dataset.harvest_run_id = run.id
        session.add(dataset)
    for attribute in (
        "lineage", "policies", "grants", "usage", "dq_monitors", "dq_incidents",
        "ml_assets", "semantic_models", "kpi_definitions", "agents", "rag_corpora",
        "governance_programs",
    ):
        for entity in getattr(bundle, attribute):
            entity.tenant_id = tenant.id
            session.add(entity)
    session.flush()


def harvest_connector(session: Session, tenant: Tenant, connector_key: str, config: dict | None = None) -> HarvestRun:
    """Run one connector and persist what it returns."""
    run = HarvestRun(tenant_id=tenant.id, connector_key=connector_key, status="running")
    session.add(run)
    session.flush()
    connector = build_connector(connector_key, config or {})
    try:
        bundle = connector.harvest()
    except Exception as exc:  # noqa: BLE001 - recorded on the run and re-raised
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        session.flush()
        raise PipelineError(f"harvest failed for connector {connector_key!r}: {exc}") from exc

    persist_bundle(session, tenant, run, bundle)
    run.status = "complete"
    run.finished_at = datetime.now(timezone.utc)
    run.stats = {
        **bundle.stats(),
        "capabilities": sorted(bundle.capabilities),
        "warnings": bundle.warnings,
        # Non-secret provenance only -- see Connector.config_summary.
        "config": connector.config_summary(),
    }
    session.flush()
    return run


def load_estate(session: Session, tenant: Tenant, capabilities: set[str], harvested_at: datetime) -> Estate:
    """Materialise the canonical model for the check library."""
    datasets = list(
        session.scalars(
            select(Dataset).where(Dataset.tenant_id == tenant.id).options(selectinload(Dataset.columns))
        )
    )

    def load(model):
        return list(session.scalars(select(model).where(model.tenant_id == tenant.id)))

    return Estate(
        tenant_key=tenant.key,
        harvested_at=harvested_at,
        datasets=datasets,
        lineage=load(LineageEdge),
        policies=load(Policy),
        grants=load(Grant),
        usage=load(UsageEvent),
        dq_monitors=load(DQMonitor),
        dq_incidents=load(DQIncident),
        ml_assets=load(MLAsset),
        semantic_models=load(SemanticModel),
        kpi_definitions=load(KPIDefinition),
        agents=load(AgentAsset),
        rag_corpora=load(RAGCorpus),
        governance_programs=load(GovernanceProgram),
        questionnaire=load(QuestionnaireResponse),
        capabilities=frozenset(capabilities),
        platforms=tuple(sorted({d.platform for d in datasets})),
    )


def _snapshot_id(tenant_key: str, rubric_version: str, harvested_at: datetime, sequence: int) -> str:
    seed = f"{tenant_key}|{rubric_version}|{harvested_at.isoformat()}|{sequence}"
    return f"snap_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def run_assessment(
    session: Session,
    tenant: Tenant,
    connectors: list[tuple[str, dict]] | None = None,
    *,
    rubric_version: str | None = None,
    label: str = "",
    harvested_at: datetime | None = None,
    generate_advice: bool = True,
) -> Assessment:
    """Execute a full assessment run and freeze it as an immutable snapshot."""
    settings = get_settings()
    rubric_version = rubric_version or settings.default_rubric_version
    rubric = get_rubric(session, rubric_version) or install_rubric(session, rubric_version)

    connectors = connectors or [("demo", {})]
    harvested_at = harvested_at or datetime.now(timezone.utc)

    _wipe_canonical(session, tenant.id)
    capabilities: set[str] = set()
    connector_summaries = []
    for connector_key, config in connectors:
        run = harvest_connector(session, tenant, connector_key, config)
        capabilities |= set(run.stats.get("capabilities", []))
        connector_summaries.append({"connector": connector_key, "harvest_run_id": run.id, "stats": run.stats})

    estate = load_estate(session, tenant, capabilities, harvested_at)
    records, skipped = run_checks(estate)
    if not records:
        raise PipelineError("no evidence was produced; refusing to write an empty snapshot")

    sequence = session.scalar(
        select(Assessment.id).where(Assessment.tenant_id == tenant.id).order_by(Assessment.id.desc())
    ) or 0
    assessment = Assessment(
        tenant_id=tenant.id,
        snapshot_id=_snapshot_id(tenant.key, rubric_version, harvested_at, sequence + 1),
        rubric_version=rubric_version,
        label=label or f"{tenant.name} readiness assessment",
        status="running",
        harvested_at=harvested_at,
        connectors=connector_summaries,
    )
    session.add(assessment)
    session.flush()

    evidence = [
        Evidence(
            assessment_id=assessment.id,
            check_id=record.check_id,
            check_title=record.check_title,
            pillar_key=record.pillar_key,
            platform=record.platform,
            domain=record.domain,
            target_urn=record.target_urn,
            target_type=record.target_type,
            result=round(record.result, 4),
            measured=record.measured,
            confidence=record.confidence,
            rationale=record.rationale,
            severity=record.severity,
            failing_targets=record.failing_targets,
        )
        for record in records
    ]
    session.add_all(evidence)
    session.flush()  # assign evidence ids before scoring so score lines can cite them

    result = score_assessment(rubric, evidence)
    session.add_all(persist_scores(assessment, result))

    assessment.stats = {
        "evidence_records": len(evidence),
        "pending_review": len(result.pending_review_evidence),
        "checks_skipped": skipped,
        "unmeasured_criteria": result.unmeasured_criteria,
        "caps_applied": result.caps_applied,
        "blockers_triggered": result.blockers_triggered,
        "datasets": len(estate.datasets),
        "tier1_datasets": len(estate.tier1),
        "platforms": list(estate.platforms),
        "grade_interpretation": result.interpretation,
    }
    assessment.status = "complete"
    assessment.frozen_at = datetime.now(timezone.utc)
    assessment.snapshot_hash = snapshot_hash(rubric_version, evidence, result)
    session.flush()

    if generate_advice:
        recommendations = generate_recommendations(rubric, assessment, evidence, result)
        session.add_all(recommendations)
        session.flush()

    return assessment


def rescore(session: Session, assessment: Assessment) -> tuple[str, str | None]:
    """Re-run scoring over a frozen snapshot's evidence.

    Returns ``(new_hash, previous_hash)``. For an untouched snapshot the two are
    equal -- that identity is the reproducibility guarantee, and the golden tests
    assert it.
    """
    rubric = get_rubric(session, assessment.rubric_version)
    if rubric is None:
        raise PipelineError(f"rubric {assessment.rubric_version} is not installed")
    evidence = list(session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id)))
    result = score_assessment(rubric, evidence)
    session.execute(delete(Score).where(Score.assessment_id == assessment.id))
    session.add_all(persist_scores(assessment, result))
    previous = assessment.snapshot_hash
    assessment.snapshot_hash = snapshot_hash(assessment.rubric_version, evidence, result)
    session.flush()
    return assessment.snapshot_hash, previous
