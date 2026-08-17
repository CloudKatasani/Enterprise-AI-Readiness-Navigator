"""Role-scoped dashboard views over a frozen snapshot.

Three personas, one snapshot (blueprint S16):

* **Executive** -- composite, grade, trend, cohort percentile, top risks, roadmap.
* **Architect** -- pillar heatmap by platform and domain, with drill-through from
  any score to the evidence records that produced it.
* **Steward** -- the findings queue, the low-confidence review queue, and the
  certification workload.

Every number these views return carries the evidence IDs behind it. If a number
cannot be traced to evidence, it does not belong on the dashboard.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.benchmarks import benchmark
from eairn.models import (
    AdvisorNarrative,
    Assessment,
    Evidence,
    Recommendation,
    Score,
    Tenant,
)
from eairn.recommend.engine import sequence_roadmap

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def serialize_evidence(record: Evidence, *, include_failing: bool = False) -> dict[str, Any]:
    payload = {
        "id": record.id,
        "check_id": record.check_id,
        "check_title": record.check_title,
        "pillar_key": record.pillar_key,
        "platform": record.platform,
        "domain": record.domain,
        "target_urn": record.target_urn,
        "target_type": record.target_type,
        "result": record.result,
        "measured": record.measured,
        "confidence": record.confidence,
        "rationale": record.rationale,
        "severity": record.severity,
        "status": record.status,
        "failing_target_count": len(record.failing_targets or []),
        "reviewed_by": record.reviewed_by,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "review_note": record.review_note,
    }
    if include_failing:
        payload["failing_targets"] = record.failing_targets or []
    return payload


def serialize_score(score: Score) -> dict[str, Any]:
    return {
        "scope": score.scope,
        "key": score.key,
        "parent_key": score.parent_key,
        "name": score.name,
        "score": score.score,
        "raw_score": score.raw_score,
        "weight": score.weight,
        "grade": score.grade,
        "capped_by": score.capped_by,
        "evidence_ids": score.evidence_ids,
    }


def serialize_recommendation(rec: Recommendation) -> dict[str, Any]:
    return {
        "id": rec.id,
        "playbook_id": rec.playbook_id,
        "title": rec.title,
        "pillar_key": rec.pillar_key,
        "horizon": rec.horizon,
        "summary": rec.summary,
        "steps": rec.steps,
        "effort_days": rec.effort_days,
        "cost_estimate": rec.cost_estimate,
        "projected_criterion_score": rec.projected_criterion_score,
        "composite_impact": rec.composite_impact,
        "unblocks": rec.unblocks,
        "confidence": rec.confidence,
        "rationale": rec.rationale,
        "evidence_ids": rec.evidence_ids,
        "generator": rec.generator,
        "status": rec.status,
        "reviewed_by": rec.reviewed_by,
        "reviewed_at": rec.reviewed_at.isoformat() if rec.reviewed_at else None,
    }


def serialize_assessment(assessment: Assessment) -> dict[str, Any]:
    return {
        "snapshot_id": assessment.snapshot_id,
        "tenant": assessment.tenant.name if assessment.tenant else None,
        "tenant_key": assessment.tenant.key if assessment.tenant else None,
        "label": assessment.label,
        "status": assessment.status,
        "rubric_version": assessment.rubric_version,
        "harvested_at": assessment.harvested_at.isoformat() if assessment.harvested_at else None,
        "frozen_at": assessment.frozen_at.isoformat() if assessment.frozen_at else None,
        "snapshot_hash": assessment.snapshot_hash,
        "composite_score": assessment.composite_score,
        "grade": assessment.grade,
        "ari_score": assessment.ari_score,
        "ari_grade": assessment.ari_grade,
        "rri_score": assessment.rri_score,
        "rri_grade": assessment.rri_grade,
        "connectors": assessment.connectors,
        "stats": assessment.stats,
    }


#: Industry keys are stored machine-readable; these are the labels a reader sees.
INDUSTRY_LABELS = {
    "financial_services": "Financial Services",
    "telecommunications": "Telecommunications",
    "retail": "Retail & Consumer",
    "utilities": "Utilities & Energy",
    "technology": "Technology & Software",
    "healthcare": "Healthcare & Life Sciences",
    "manufacturing": "Manufacturing",
    "public_sector": "Public Sector",
    "unspecified": "Unclassified",
}


def industry_label(key: str) -> str:
    return INDUSTRY_LABELS.get(key, key.replace("_", " ").title())


def portfolio(session: Session) -> list[dict[str, Any]]:
    """Every assessed organisation, grouped by industry, latest snapshot each.

    This is the entry point to the executive view: a CDO comparing their estate
    to a peer's needs to see both, and a delivery partner running several
    assessments needs one place to pick between them.
    """
    tenants = list(session.scalars(select(Tenant).order_by(Tenant.name)))
    by_industry: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for tenant in tenants:
        latest = session.scalar(
            select(Assessment)
            .where(Assessment.tenant_id == tenant.id, Assessment.status == "complete")
            .order_by(Assessment.id.desc())
        )
        if latest is None:
            continue
        stats = latest.stats or {}
        # Count blocking *findings*, not just caps that bound: an estate already
        # below a cap still has the finding, and hiding it would flatter it.
        blockers = stats.get("blockers_triggered") or stats.get("caps_applied", [])
        by_industry[tenant.industry].append(
            {
                "tenant_key": tenant.key,
                "tenant": tenant.name,
                "size_band": tenant.size_band,
                "snapshot_id": latest.snapshot_id,
                "label": latest.label,
                "harvested_at": latest.harvested_at.isoformat() if latest.harvested_at else None,
                "composite_score": latest.composite_score,
                "grade": latest.grade,
                "grade_interpretation": (latest.stats or {}).get("grade_interpretation", ""),
                "ari_score": latest.ari_score,
                "ari_grade": latest.ari_grade,
                "rri_score": latest.rri_score,
                "rri_grade": latest.rri_grade,
                "hard_blockers": len({b["scope"] for b in blockers}),
                "hard_blockers_binding": len(
                    {b["scope"] for b in blockers if b.get("applied", True)}
                ),
                "evidence_records": (latest.stats or {}).get("evidence_records", 0),
                "assessment_count": len(
                    [a for a in tenant.assessments if a.status == "complete"]
                ),
            }
        )

    return [
        {
            "industry": key,
            "industry_label": industry_label(key),
            "organisations": sorted(
                orgs, key=lambda o: (o["composite_score"] is None, -(o["composite_score"] or 0))
            ),
            "median_composite": round(
                sorted(o["composite_score"] for o in orgs if o["composite_score"] is not None)[
                    len([o for o in orgs if o["composite_score"] is not None]) // 2
                ],
                1,
            )
            if any(o["composite_score"] is not None for o in orgs)
            else None,
        }
        for key, orgs in sorted(by_industry.items(), key=lambda kv: industry_label(kv[0]))
    ]


def _load(session: Session, assessment: Assessment):
    scores = list(session.scalars(select(Score).where(Score.assessment_id == assessment.id)))
    evidence = list(session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id)))
    recommendations = list(
        session.scalars(select(Recommendation).where(Recommendation.assessment_id == assessment.id))
    )
    return scores, evidence, recommendations


def executive_view(session: Session, assessment: Assessment) -> dict[str, Any]:
    scores, evidence, recommendations = _load(session, assessment)
    tenant = assessment.tenant or session.get(Tenant, assessment.tenant_id)
    evidence_by_id = {e.id: e for e in evidence}

    metrics = {"composite": assessment.composite_score}
    for score in scores:
        if score.scope == "pillar":
            metrics[score.key] = score.score
    if assessment.ari_score is not None:
        metrics["ARI"] = assessment.ari_score
    if assessment.rri_score is not None:
        metrics["RRI"] = assessment.rri_score

    # Metric keys are machine-readable; the reader gets the rubric's own names,
    # so an index appears as "Agent Readiness Index" rather than "ARI".
    labels = {"composite": "Composite readiness"}
    labels.update({s.key: s.name for s in scores if s.scope in {"pillar", "index"}})
    benchmarks = [
        {**b.as_dict(), "label": labels.get(b.metric_key, b.metric_key)}
        for b in benchmark(session, tenant, metrics)
    ]

    # Top risks: severity first, then how far the check is from its target.
    risks = sorted(
        (e for e in evidence if e.severity in {"critical", "high"}),
        key=lambda e: (SEVERITY_ORDER.get(e.severity, 9), e.result),
    )[:5]

    trend = _trend(session, assessment)
    ranked = sorted(recommendations, key=lambda r: -r.composite_impact)
    roadmap = sequence_roadmap(ranked)
    narrative = session.scalar(
        select(AdvisorNarrative)
        .where(AdvisorNarrative.assessment_id == assessment.id)
        .order_by(AdvisorNarrative.id.desc())
    )

    return {
        "assessment": serialize_assessment(assessment),
        "industry": tenant.industry if tenant else None,
        "industry_label": industry_label(tenant.industry) if tenant else None,
        "grade_interpretation": (assessment.stats or {}).get("grade_interpretation", ""),
        "pillars": [serialize_score(s) for s in scores if s.scope == "pillar"],
        "indices": [serialize_score(s) for s in scores if s.scope == "index"],
        "benchmarks": benchmarks,
        "trend": trend,
        "caps_applied": (assessment.stats or {}).get("blockers_triggered")
        or (assessment.stats or {}).get("caps_applied", []),
        "top_risks": [serialize_evidence(e) for e in risks],
        "roadmap": [
            {
                **horizon,
                "recommendations": [
                    serialize_recommendation(r)
                    for r in ranked
                    if r.id in set(horizon["recommendations"])
                ],
            }
            for horizon in roadmap
        ],
        "investment": {
            "total_effort_days": round(sum(r.effort_days for r in recommendations), 1),
            "total_cost_estimate": round(sum(r.cost_estimate for r in recommendations), 2),
            "projected_composite": round(
                (assessment.composite_score or 0)
                + sum(h["projected_impact"] for h in roadmap),
                2,
            ),
        },
        "advisor_narrative": (
            {
                "body": narrative.body,
                "citations": narrative.citations,
                "generator": narrative.generator,
                "model": narrative.model,
                "confidence": narrative.confidence,
                "status": narrative.status,
                "cited_evidence": [
                    serialize_evidence(evidence_by_id[cid])
                    for cid in narrative.citations
                    if cid in evidence_by_id
                ],
            }
            if narrative
            else None
        ),
    }


def architect_view(session: Session, assessment: Assessment) -> dict[str, Any]:
    scores, evidence, _ = _load(session, assessment)
    evidence_by_id = {e.id: e for e in evidence}

    by_platform: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_domain: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for record in evidence:
        if record.status != "accepted":
            continue
        by_platform[record.platform][record.pillar_key].append(record.result)
        if record.domain:
            by_domain[record.domain][record.pillar_key].append(record.result)

    def heatmap(source: dict[str, dict[str, list[float]]]) -> list[dict[str, Any]]:
        return [
            {
                "key": outer,
                "pillars": {
                    pillar: round(sum(values) / len(values), 2)
                    for pillar, values in inner.items()
                    if values
                },
            }
            for outer, inner in sorted(source.items())
        ]

    return {
        "assessment": serialize_assessment(assessment),
        "scores": [serialize_score(s) for s in scores],
        "heatmap_by_platform": heatmap(by_platform),
        "heatmap_by_domain": heatmap(by_domain),
        "criteria": [
            {
                **serialize_score(s),
                "evidence": [
                    serialize_evidence(evidence_by_id[eid])
                    for eid in s.evidence_ids
                    if eid in evidence_by_id
                ],
            }
            for s in scores
            if s.scope == "criterion"
        ],
        "unmeasured_criteria": (assessment.stats or {}).get("unmeasured_criteria", []),
        "checks_skipped": (assessment.stats or {}).get("checks_skipped", []),
    }


def steward_view(session: Session, assessment: Assessment) -> dict[str, Any]:
    _, evidence, recommendations = _load(session, assessment)
    review_queue = [e for e in evidence if e.status == "pending_review"]
    findings = sorted(
        (e for e in evidence if e.failing_targets and e.status == "accepted"),
        key=lambda e: (SEVERITY_ORDER.get(e.severity, 9), e.result),
    )
    return {
        "assessment": serialize_assessment(assessment),
        "review_queue": [serialize_evidence(e, include_failing=True) for e in review_queue],
        "findings_queue": [serialize_evidence(e, include_failing=True) for e in findings[:50]],
        "draft_recommendations": [
            serialize_recommendation(r) for r in recommendations if r.status == "draft"
        ],
        "workload": {
            "pending_review": len(review_queue),
            "open_findings": len(findings),
            "failing_targets": sum(len(e.failing_targets or []) for e in findings),
        },
    }


def _trend(session: Session, assessment: Assessment) -> list[dict[str, Any]]:
    history = list(
        session.scalars(
            select(Assessment)
            .where(
                Assessment.tenant_id == assessment.tenant_id,
                Assessment.status == "complete",
                Assessment.id <= assessment.id,
            )
            .order_by(Assessment.id)
        )
    )
    return [
        {
            "snapshot_id": a.snapshot_id,
            "harvested_at": a.harvested_at.isoformat() if a.harvested_at else None,
            "composite_score": a.composite_score,
            "grade": a.grade,
            "ari_score": a.ari_score,
            "rri_score": a.rri_score,
        }
        for a in history[-8:]
    ]
