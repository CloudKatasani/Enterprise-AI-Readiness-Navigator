"""HTTP API for the Portal and for partner-delivered assessments."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.advisor import AdvisorInput, draft_executive_narrative
from eairn.api.schemas import (
    AssessmentRun,
    EvidenceReview,
    QuestionnaireSubmission,
    RecommendationReview,
    SamplingAuthorizationCreate,
    SimulationRequest,
    TenantCreate,
)
from eairn.checks import REGISTRY as CHECK_REGISTRY
from eairn.config import get_settings
from eairn.connectors import describe_all
from eairn.dashboard import (
    architect_view,
    executive_view,
    portfolio,
    serialize_assessment,
    serialize_evidence,
    serialize_recommendation,
    serialize_score,
    steward_view,
)
from eairn.db import get_session
from eairn.methodology import median_assessment, methodology_view
from eairn.pillars import pillar_guide
from eairn.models import (
    AdvisorNarrative,
    Assessment,
    Evidence,
    QuestionnaireResponse,
    Recommendation,
    SamplingAuthorization,
    Score,
    Tenant,
)
from eairn.pipeline import rescore, run_assessment
from eairn.questionnaire import QUESTIONNAIRE
from eairn.recommend.engine import load_playbooks
from eairn.rubric import get_rubric, install_rubric
from eairn.scoring import score_assessment, simulate_uplift, snapshot_hash

router = APIRouter()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _tenant(session: Session, key: str) -> Tenant:
    tenant = session.scalar(select(Tenant).where(Tenant.key == key))
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"unknown tenant {key!r}")
    return tenant


def _assessment(session: Session, snapshot_id: str) -> Assessment:
    assessment = session.scalar(select(Assessment).where(Assessment.snapshot_id == snapshot_id))
    if assessment is None:
        raise HTTPException(status_code=404, detail=f"unknown snapshot {snapshot_id!r}")
    return assessment


def _evidence_for(session: Session, assessment: Assessment) -> list[Evidence]:
    return list(session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id)))


# --------------------------------------------------------------------------- #
# catalog
# --------------------------------------------------------------------------- #


@router.get("/connectors", tags=["catalog"])
def list_connectors() -> dict[str, Any]:
    """Connector catalog with the permission manifest published to the customer."""
    return {"connectors": describe_all()}


@router.get("/checks", tags=["catalog"])
def list_checks() -> dict[str, Any]:
    return {
        "checks": [
            {
                "check_id": spec.check_id,
                "title": spec.title,
                "pillar": spec.pillar_key,
                "requires": sorted(spec.requires),
                "description": spec.description,
            }
            for spec in sorted(CHECK_REGISTRY.values(), key=lambda s: s.check_id)
        ]
    }


@router.get("/playbooks", tags=["catalog"])
def list_playbooks() -> dict[str, Any]:
    library = load_playbooks()
    return {
        "version": library.version,
        "day_rate": library.day_rate,
        "playbooks": [
            {
                "id": p.id,
                "check_id": p.check_id,
                "title": p.title,
                "pillar": p.pillar,
                "horizon": p.horizon,
                "target": p.target,
                "effort_days": p.effort_days,
                "summary": p.summary,
                "steps": list(p.steps),
                "rationale": p.rationale,
                "unblocks": list(p.unblocks),
            }
            for p in library.playbooks
        ],
    }


@router.get("/rubrics/{version}", tags=["catalog"])
def get_rubric_detail(version: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    rubric = get_rubric(session, version)
    if rubric is None:
        try:
            rubric = install_rubric(session, version)
            session.commit()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "version": rubric.version,
        "name": rubric.name,
        "confidence_threshold": rubric.confidence_threshold,
        "source_digest": rubric.source_digest,
        "pillars": [
            {
                "key": p.key,
                "name": p.name,
                "weight": p.weight,
                "scoring_mode": p.scoring_mode,
                "core_question": p.core_question,
                "rationale": p.rationale,
                "criteria": [
                    {
                        "key": c.key,
                        "name": c.name,
                        "check_id": c.check_id,
                        "weight": c.weight,
                        "target": c.target,
                        "description": c.description,
                    }
                    for c in sorted(p.criteria, key=lambda c: c.key)
                ],
            }
            for p in sorted(rubric.pillars, key=lambda p: -p.weight)
        ],
        "overrides": [
            {
                "key": o.key,
                "check_id": o.check_id,
                "condition": o.condition,
                "threshold": o.threshold,
                "cap_scope": o.cap_scope,
                "cap_value": o.cap_value,
                "rationale": o.rationale,
            }
            for o in rubric.overrides
        ],
        "indices": {
            index_key: [
                {
                    "key": d.key,
                    "name": d.name,
                    "weight": d.weight,
                    "description": d.description,
                    "check_ids": d.check_ids,
                }
                for d in rubric.dimensions
                if d.index_key == index_key
            ]
            for index_key in sorted({d.index_key for d in rubric.dimensions})
        },
        "grade_bands": [
            {
                "scope": b.scope,
                "min": b.min_score,
                "max": b.max_score,
                "grade": b.grade,
                "interpretation": b.interpretation,
            }
            for b in sorted(rubric.bands, key=lambda b: (b.scope, -b.min_score))
        ],
    }


@router.get("/questionnaire", tags=["catalog"])
def get_questionnaire() -> dict[str, Any]:
    return {"sections": QUESTIONNAIRE}


@router.get("/pillars", tags=["catalog"])
def get_pillar_guide(
    version: str | None = Query(default=None, description="Rubric version; defaults to the active one"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Why each pillar exists, what it costs to omit it, and where to read more."""
    version = version or get_settings().default_rubric_version
    rubric = get_rubric(session, version)
    if rubric is None:
        try:
            rubric = install_rubric(session, version)
            session.commit()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return pillar_guide(session, rubric)


@router.get("/methodology", tags=["catalog"])
def get_methodology(
    snapshot: str | None = Query(default=None, description="Worked example; defaults to the median estate"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """How a score is produced, worked through one snapshot's own evidence."""
    assessment = _assessment(session, snapshot) if snapshot else median_assessment(session)
    if assessment is None:
        raise HTTPException(status_code=404, detail="no completed assessment to explain")
    rubric = get_rubric(session, assessment.rubric_version)
    if rubric is None:
        raise HTTPException(
            status_code=409, detail=f"rubric {assessment.rubric_version} is not installed"
        )
    return {
        "default_snapshot": assessment.snapshot_id,
        "requested_snapshot": snapshot,
        **methodology_view(session, assessment, rubric),
    }


# --------------------------------------------------------------------------- #
# tenants
# --------------------------------------------------------------------------- #


@router.get("/portfolio", tags=["dashboard"])
def get_portfolio(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Assessed organisations grouped by industry, latest snapshot each."""
    return {"industries": portfolio(session)}


@router.get("/tenants", tags=["tenants"])
def list_tenants(session: Session = Depends(get_session)) -> dict[str, Any]:
    tenants = session.scalars(select(Tenant).order_by(Tenant.id)).all()
    return {
        "tenants": [
            {
                "key": t.key,
                "name": t.name,
                "industry": t.industry,
                "size_band": t.size_band,
                "assessments": len(t.assessments),
            }
            for t in tenants
        ]
    }


@router.post("/tenants", tags=["tenants"], status_code=201)
def create_tenant(body: TenantCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    if session.scalar(select(Tenant).where(Tenant.key == body.key)):
        raise HTTPException(status_code=409, detail=f"tenant {body.key!r} already exists")
    tenant = Tenant(**body.model_dump())
    session.add(tenant)
    session.commit()
    return {"key": tenant.key, "name": tenant.name}


@router.post("/questionnaire", tags=["tenants"], status_code=201)
def submit_questionnaire(
    body: QuestionnaireSubmission, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Supplementary evidence. Cross-validated against machine evidence by GV-009."""
    tenant = _tenant(session, body.tenant_key)
    for answer in body.responses:
        session.add(
            QuestionnaireResponse(
                tenant_id=tenant.id,
                question_id=answer.question_id,
                question=answer.question,
                answer=answer.answer,
                numeric_answer=answer.numeric_answer,
                respondent=answer.respondent,
            )
        )
    session.commit()
    return {"recorded": len(body.responses)}


@router.post("/sampling-authorizations", tags=["tenants"], status_code=201)
def authorize_sampling(
    body: SamplingAuthorizationCreate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Explicit, logged, per-dataset authorization for the optional sampling module.

    Recording an authorization does not enable sampling: the default build has no
    row-data access path at all, and the sampling module is a separate,
    permission-gated package.
    """
    settings = get_settings()
    tenant = _tenant(session, body.tenant_key)
    record = SamplingAuthorization(
        tenant_id=tenant.id,
        dataset_urn=body.dataset_urn,
        authorized_by=body.authorized_by,
        justification=body.justification,
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days),
    )
    session.add(record)
    session.commit()
    return {
        "id": record.id,
        "dataset_urn": record.dataset_urn,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "sampling_module_installed": settings.allow_row_sampling,
        "note": (
            "Authorization logged. Row sampling remains unavailable in this build; the "
            "optional module must be installed separately and will honour this record."
        ),
    }


# --------------------------------------------------------------------------- #
# assessments
# --------------------------------------------------------------------------- #


@router.post("/assessments", tags=["assessments"], status_code=201)
def create_assessment(body: AssessmentRun, session: Session = Depends(get_session)) -> dict[str, Any]:
    tenant = _tenant(session, body.tenant_key)
    connectors = [(c.connector, c.config) for c in body.connectors]
    try:
        assessment = run_assessment(
            session,
            tenant,
            connectors,
            rubric_version=body.rubric_version,
            label=body.label,
            generate_advice=body.generate_advice,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller with context
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return serialize_assessment(assessment)


@router.get("/assessments", tags=["assessments"])
def list_assessments(
    tenant_key: str | None = None, session: Session = Depends(get_session)
) -> dict[str, Any]:
    statement = select(Assessment).order_by(Assessment.id.desc())
    if tenant_key:
        statement = statement.where(Assessment.tenant_id == _tenant(session, tenant_key).id)
    return {"assessments": [serialize_assessment(a) for a in session.scalars(statement)]}


@router.get("/assessments/{snapshot_id}", tags=["assessments"])
def get_assessment(snapshot_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return serialize_assessment(_assessment(session, snapshot_id))


@router.get("/assessments/{snapshot_id}/scores", tags=["assessments"])
def get_scores(snapshot_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    assessment = _assessment(session, snapshot_id)
    scores = session.scalars(select(Score).where(Score.assessment_id == assessment.id))
    return {"scores": [serialize_score(s) for s in scores]}


@router.get("/assessments/{snapshot_id}/evidence", tags=["assessments"])
def get_evidence(
    snapshot_id: str,
    pillar: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    check_id: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    assessment = _assessment(session, snapshot_id)
    statement = select(Evidence).where(Evidence.assessment_id == assessment.id)
    if pillar:
        statement = statement.where(Evidence.pillar_key == pillar)
    if status:
        statement = statement.where(Evidence.status == status)
    if severity:
        statement = statement.where(Evidence.severity == severity)
    if check_id:
        statement = statement.where(Evidence.check_id == check_id)
    records = session.scalars(statement.order_by(Evidence.result))
    return {"evidence": [serialize_evidence(e) for e in records]}


@router.get("/evidence/{evidence_id}", tags=["assessments"])
def get_evidence_detail(evidence_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    record = session.get(Evidence, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return serialize_evidence(record, include_failing=True)


@router.post("/evidence/{evidence_id}/review", tags=["assessments"])
def review_evidence(
    evidence_id: int, body: EvidenceReview, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Accept or reject a low-confidence finding, then re-score the snapshot.

    A reviewer decision is the only thing that overrides the confidence
    threshold, and it is recorded with the reviewer's name on the evidence row.
    """
    record = session.get(Evidence, evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    record.status = body.decision
    record.reviewed_by = body.reviewer
    record.reviewed_at = datetime.now(timezone.utc)
    record.review_note = body.note
    session.flush()

    assessment = session.get(Assessment, record.assessment_id)
    new_hash, previous_hash = rescore(session, assessment)
    session.commit()
    return {
        "evidence": serialize_evidence(record),
        "snapshot_hash": new_hash,
        "previous_snapshot_hash": previous_hash,
        "composite_score": assessment.composite_score,
        "grade": assessment.grade,
    }


@router.get("/assessments/{snapshot_id}/recommendations", tags=["assessments"])
def get_recommendations(snapshot_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    assessment = _assessment(session, snapshot_id)
    records = session.scalars(
        select(Recommendation)
        .where(Recommendation.assessment_id == assessment.id)
        .order_by(Recommendation.composite_impact.desc())
    )
    return {"recommendations": [serialize_recommendation(r) for r in records]}


@router.post("/recommendations/{recommendation_id}/review", tags=["assessments"])
def review_recommendation(
    recommendation_id: int, body: RecommendationReview, session: Session = Depends(get_session)
) -> dict[str, Any]:
    record = session.get(Recommendation, recommendation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    record.status = body.decision
    record.reviewed_by = body.reviewer
    record.reviewed_at = datetime.now(timezone.utc)
    record.review_note = body.note
    session.commit()
    return serialize_recommendation(record)


@router.post("/assessments/{snapshot_id}/simulate", tags=["assessments"])
def simulate(
    snapshot_id: str, body: SimulationRequest, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """What-if: move named checks to target values and re-score, without mutating anything."""
    assessment = _assessment(session, snapshot_id)
    rubric = get_rubric(session, assessment.rubric_version)
    if rubric is None:
        raise HTTPException(status_code=409, detail="rubric for this snapshot is not installed")
    unknown = sorted(set(body.targets) - set(CHECK_REGISTRY))
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown check id(s): {', '.join(unknown)}")
    evidence = _evidence_for(session, assessment)
    uplift = simulate_uplift(rubric, evidence, body.targets)
    return {"snapshot_id": snapshot_id, "targets": body.targets, **uplift.as_dict()}


@router.get("/assessments/{snapshot_id}/verify", tags=["assessments"])
def verify_snapshot(snapshot_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Replay the scoring engine over the frozen evidence and compare hashes.

    An unchanged snapshot must reproduce its recorded hash exactly. This is the
    endpoint an auditor calls.
    """
    assessment = _assessment(session, snapshot_id)
    rubric = get_rubric(session, assessment.rubric_version)
    if rubric is None:
        raise HTTPException(status_code=409, detail="rubric for this snapshot is not installed")
    evidence = _evidence_for(session, assessment)
    result = score_assessment(rubric, evidence)
    replayed = snapshot_hash(assessment.rubric_version, evidence, result)
    return {
        "snapshot_id": snapshot_id,
        "rubric_version": assessment.rubric_version,
        "rubric_source_digest": rubric.source_digest,
        "recorded_hash": assessment.snapshot_hash,
        "replayed_hash": replayed,
        "reproducible": replayed == assessment.snapshot_hash,
        "recorded_composite": assessment.composite_score,
        "replayed_composite": result.composite,
    }


@router.get("/assessments/{snapshot_id}/advisor", tags=["assessments"])
def get_advisor_narrative(
    snapshot_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    assessment = _assessment(session, snapshot_id)
    narrative = session.scalar(
        select(AdvisorNarrative)
        .where(AdvisorNarrative.assessment_id == assessment.id)
        .order_by(AdvisorNarrative.id.desc())
    )
    if narrative is None:
        raise HTTPException(status_code=404, detail="no narrative drafted for this snapshot")
    return _serialize_narrative(narrative)


@router.post("/assessments/{snapshot_id}/advisor", tags=["assessments"], status_code=201)
def draft_advisor_narrative(
    snapshot_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    assessment = _assessment(session, snapshot_id)
    scores = list(session.scalars(select(Score).where(Score.assessment_id == assessment.id)))
    evidence = _evidence_for(session, assessment)
    recommendations = list(
        session.scalars(
            select(Recommendation)
            .where(Recommendation.assessment_id == assessment.id)
            .order_by(Recommendation.composite_impact.desc())
        )
    )
    narrative = draft_executive_narrative(
        AdvisorInput(
            assessment=assessment,
            scores=scores,
            evidence=evidence,
            recommendations=recommendations,
        )
    )
    session.add(narrative)
    session.commit()
    return _serialize_narrative(narrative)


@router.get("/assessments/{snapshot_id}/dashboard/{role}", tags=["dashboard"])
def get_dashboard(
    snapshot_id: str,
    role: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    assessment = _assessment(session, snapshot_id)
    views = {"executive": executive_view, "architect": architect_view, "steward": steward_view}
    view = views.get(role)
    if view is None:
        raise HTTPException(
            status_code=404, detail=f"unknown role {role!r}; expected one of {', '.join(views)}"
        )
    return view(session, assessment)


@router.get("/assessments/{snapshot_id}/benchmarks", tags=["dashboard"])
def get_benchmarks(
    snapshot_id: str,
    metric: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from eairn.benchmarks import benchmark  # local import keeps the router import graph flat

    assessment = _assessment(session, snapshot_id)
    scores = session.scalars(select(Score).where(Score.assessment_id == assessment.id)).all()
    metrics: dict[str, float | None] = {"composite": assessment.composite_score}
    metrics.update({s.key: s.score for s in scores if s.scope == "pillar"})
    metrics["ARI"] = assessment.ari_score
    metrics["RRI"] = assessment.rri_score
    results = benchmark(session, assessment.tenant, metrics, keys=metric)
    return {"benchmarks": [r.as_dict() for r in results]}


def _serialize_narrative(narrative: AdvisorNarrative) -> dict[str, Any]:
    return {
        "id": narrative.id,
        "kind": narrative.kind,
        "body": narrative.body,
        "citations": narrative.citations,
        "generator": narrative.generator,
        "model": narrative.model,
        "confidence": narrative.confidence,
        "status": narrative.status,
        "created_at": narrative.created_at.isoformat() if narrative.created_at else None,
        "prompt_recorded": narrative.prompt is not None,
    }
