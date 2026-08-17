"""Methodology view: the arithmetic behind a score, shown against real evidence.

A readiness grade is only worth as much as the reader's ability to check it. This
module reconstructs, for one snapshot, every step from harvested metadata to the
composite:

    evidence record -> criterion score -> weighted pillar score -> cap -> composite

Nothing here re-scores anything. It reads the score lines the Scoring Engine
already wrote and shows the working, then recomputes each weighted sum
independently and reports whether the recomputation matches what the engine
stored. A mismatch would be a bug worth seeing, so it is surfaced rather than
hidden.

The same view reports what was *not* measured -- unmeasured criteria, checks
skipped for missing connector capability, evidence held below the confidence
threshold, and the data EAIRN never reads at all -- because a coverage gap that
is invisible reads as a passing score.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from eairn.checks import REGISTRY as CHECK_REGISTRY
from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    CONFIDENCE_DERIVED,
    CONFIDENCE_INFERRED,
    CONFIDENCE_RECONCILED,
    CONFIDENCE_SELF_REPORTED,
)
from eairn.config import get_settings
from eairn.dashboard import industry_label, serialize_assessment, serialize_evidence
from eairn.models import (
    AgentAsset,
    Assessment,
    Dataset,
    DQMonitor,
    Evidence,
    Grant,
    MLAsset,
    Policy,
    RAGCorpus,
    Rubric,
    Score,
    SemanticModel,
    Tenant,
)
from eairn.rubric import grade_for

#: What each confidence value means, in the reader's language. The scoring
#: threshold decides which of these reach a score; the rest queue for review.
CONFIDENCE_TIERS = (
    {
        "key": "declared",
        "value": CONFIDENCE_DECLARED,
        "label": "Declared",
        "meaning": "Read straight out of a system catalog — the platform states it as fact.",
        "example": "A masking policy attached to a column, as Snowflake reports it.",
    },
    {
        "key": "reconciled",
        "value": CONFIDENCE_RECONCILED,
        "label": "Reconciled",
        "meaning": "The same fact agreed by two independent sources.",
        "example": "Ownership in the catalog matching ownership in the governance tool.",
    },
    {
        "key": "derived",
        "value": CONFIDENCE_DERIVED,
        "label": "Derived",
        "meaning": "Computed from declared facts, with the computation stated.",
        "example": "Lineage depth obtained by traversing declared edges.",
    },
    {
        "key": "inferred",
        "value": CONFIDENCE_INFERRED,
        "label": "Inferred",
        "meaning": "A heuristic reading of the evidence. Below the threshold by design.",
        "example": "Treating a column named NATIONAL_ID as personal data with no classification set.",
    },
    {
        "key": "self_reported",
        "value": CONFIDENCE_SELF_REPORTED,
        "label": "Self-reported",
        "meaning": "A questionnaire answer with no machine evidence behind it.",
        "example": "“We have full column-level lineage” — recorded, never scored on its own.",
    },
)

#: Deliberate non-collection. These are product boundaries, not gaps to close,
#: and a reader comparing EAIRN to a profiling tool needs them stated plainly.
NEVER_COLLECTED = (
    {
        "item": "Row data and column values",
        "why": "Readiness is measured from metadata. No check reads a customer row, so no "
        "customer data can leak into a score, a narrative or a benchmark.",
    },
    {
        "item": "Query result sets",
        "why": "Connectors read catalog and governance surfaces only; every statement they "
        "may issue is published in the connector catalog and asserted read-only in CI.",
    },
    {
        "item": "Credentials and connection secrets",
        "why": "A harvest records how an estate was read — profile, platform, capabilities — "
        "never the account or token used to read it.",
    },
    {
        "item": "Free-text business content",
        "why": "Document and corpus checks count objects and their controls; they do not "
        "index or store the documents themselves.",
    },
)


def _round(value: float | None, places: int = 2) -> float | None:
    return None if value is None else round(value, places)


def _latest_assessment(session: Session, tenant_id: int) -> Assessment | None:
    return session.scalar(
        select(Assessment)
        .where(Assessment.tenant_id == tenant_id, Assessment.status == "complete")
        .order_by(Assessment.id.desc())
    )


def median_assessment(session: Session) -> Assessment | None:
    """The estate closest to the portfolio median, as the default worked example.

    A worked example taken from the strongest estate teaches least: it has the
    fewest gaps. The median estate shows both a pillar that scores well and a
    pillar that does not.
    """
    latest: list[Assessment] = []
    for tenant in session.scalars(select(Tenant)):
        assessment = _latest_assessment(session, tenant.id)
        if assessment is not None and assessment.composite_score is not None:
            latest.append(assessment)
    if not latest:
        return session.scalar(
            select(Assessment).where(Assessment.status == "complete").order_by(Assessment.id.desc())
        )
    latest.sort(key=lambda a: a.composite_score or 0)
    return latest[len(latest) // 2]


# --------------------------------------------------------------------------- #
# provenance: what the sample data actually is
# --------------------------------------------------------------------------- #


def _sample_estate(session: Session, tenant: Tenant) -> dict[str, Any]:
    """A readable slice of the harvested estate: what a check actually sees."""
    datasets = list(
        session.scalars(
            select(Dataset)
            .where(Dataset.tenant_id == tenant.id)
            .options(selectinload(Dataset.columns))
            .order_by(Dataset.tier, Dataset.urn)
            .limit(4)
        )
    )
    policies = list(
        session.scalars(select(Policy).where(Policy.tenant_id == tenant.id).limit(3))
    )
    grants = list(session.scalars(select(Grant).where(Grant.tenant_id == tenant.id).limit(3)))
    monitors = list(
        session.scalars(select(DQMonitor).where(DQMonitor.tenant_id == tenant.id).limit(3))
    )
    agents = list(session.scalars(select(AgentAsset).where(AgentAsset.tenant_id == tenant.id).limit(3)))
    corpora = list(session.scalars(select(RAGCorpus).where(RAGCorpus.tenant_id == tenant.id).limit(3)))
    models = list(session.scalars(select(MLAsset).where(MLAsset.tenant_id == tenant.id).limit(3)))
    semantics = list(
        session.scalars(select(SemanticModel).where(SemanticModel.tenant_id == tenant.id).limit(3))
    )

    return {
        "datasets": [
            {
                "urn": d.urn,
                "name": d.name,
                "domain": d.domain,
                "tier": d.tier,
                "platform": d.platform,
                "owner": d.owner,
                "owner_verified": d.owner_verified_at is not None,
                "certified": d.certified,
                "curated": d.catalog_curated,
                "described": bool(d.description),
                "description": (d.description or "")[:160],
                "columns": [
                    {
                        "name": c.name,
                        "data_type": c.data_type,
                        "classification": c.platform_classification or c.catalog_classification,
                        "described": bool(c.description),
                        "protected": c.protected,
                        "protection_kind": c.protection_kind,
                    }
                    for c in sorted(d.columns, key=lambda c: c.ordinal)[:6]
                ],
                "column_count": len(d.columns),
            }
            for d in datasets
        ],
        "policies": [
            {
                "policy_type": p.policy_type,
                "name": p.name,
                "platform": p.platform,
                "bound_to_tag": p.bound_to_tag,
                "target_count": len(p.target_urns or []),
                "targets": (p.target_urns or [])[:2],
            }
            for p in policies
        ],
        "grants": [
            {
                "grantee": g.grantee,
                "grantee_type": g.grantee_type,
                "privilege": g.privilege,
                "object_urn": g.object_urn,
                "is_admin_role": g.is_admin_role,
            }
            for g in grants
        ],
        "dq_monitors": [
            {
                "dataset_urn": m.dataset_urn,
                "tool": m.tool,
                "check_type": m.check_type,
                "defined_as_data": m.defined_as_data,
                "enabled": m.enabled,
                "pass_rate": m.pass_rate,
            }
            for m in monitors
        ],
        "ml_assets": [
            {
                "name": m.name,
                "kind": m.kind,
                "registered": m.registered,
                "training_data_lineage": m.training_data_lineage,
                "promotion_gated": m.promotion_gated,
            }
            for m in models
        ],
        "semantic_models": [
            {
                "name": s.name,
                "platform": s.platform,
                "certified": s.certified,
                "field_count": s.field_count,
                "described_field_count": s.described_field_count,
            }
            for s in semantics
        ],
        "agents": [
            {
                "name": a.name,
                "identity_kind": a.identity_kind,
                "scoped_roles": a.scoped_roles,
                "write_actions": a.write_actions,
                "write_approval_gate": a.write_approval_gate,
                "action_audit": a.action_audit,
            }
            for a in agents
        ],
        "rag_corpora": [
            {
                "name": c.name,
                "source_system": c.source_system,
                "authoritative_doc_count": c.authoritative_doc_count,
                "indexed_doc_count": c.indexed_doc_count,
                "acl_propagated": c.acl_propagated,
                "citation_enforced": c.citation_enforced,
            }
            for c in corpora
        ],
    }


def _provenance(session: Session, assessment: Assessment, tenant: Tenant) -> dict[str, Any]:
    connectors = []
    for entry in assessment.connectors or []:
        stats = entry.get("stats") or {}
        connectors.append(
            {
                "connector": entry.get("connector"),
                "config": stats.get("config") or {},
                "capabilities": stats.get("capabilities", []),
                "warnings": stats.get("warnings", []),
                "counts": {
                    key: value
                    for key, value in stats.items()
                    if isinstance(value, int) and key != "harvest_run_id"
                },
            }
        )

    latest = _latest_assessment(session, tenant.id)
    is_latest = latest is not None and latest.id == assessment.id
    return {
        "connectors": connectors,
        # The canonical tables hold the tenant's most recent harvest, so the
        # sample rows only belong to this snapshot when it is the latest one.
        "sample_matches_snapshot": is_latest,
        "sample": _sample_estate(session, tenant) if is_latest else None,
    }


# --------------------------------------------------------------------------- #
# the arithmetic
# --------------------------------------------------------------------------- #


def _evidence_summary(records: list[Evidence]) -> list[dict[str, Any]]:
    """One row per evidence record behind a criterion, with its measurement."""
    return [
        {
            **serialize_evidence(record),
            "failing_sample": (record.failing_targets or [])[:4],
        }
        for record in sorted(records, key=lambda r: r.target_urn)[:6]
    ]


def _pillar_breakdown(
    rubric: Rubric,
    scores: list[Score],
    evidence_by_id: dict[int, Evidence],
    caps_by_scope: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    criterion_lines = {s.key: s for s in scores if s.scope == "criterion"}
    pillar_lines = {s.key: s for s in scores if s.scope == "pillar"}

    breakdown = []
    for pillar in sorted(rubric.pillars, key=lambda p: (-p.weight, p.key)):
        line = pillar_lines.get(pillar.key)
        criteria = []
        numerator = denominator = 0.0
        for criterion in sorted(pillar.criteria, key=lambda c: c.key):
            score_line = criterion_lines.get(criterion.key)
            records = (
                [evidence_by_id[eid] for eid in score_line.evidence_ids if eid in evidence_by_id]
                if score_line
                else []
            )
            if score_line is not None:
                numerator += score_line.score * criterion.weight
                denominator += criterion.weight
            criteria.append(
                {
                    "key": criterion.key,
                    "name": criterion.name,
                    "check_id": criterion.check_id,
                    "check_title": CHECK_REGISTRY[criterion.check_id].title
                    if criterion.check_id in CHECK_REGISTRY
                    else criterion.check_id,
                    "description": criterion.description,
                    # What the check itself documents it measures, as distinct
                    # from what the rubric says the criterion is for.
                    "check_description": CHECK_REGISTRY[criterion.check_id].description
                    if criterion.check_id in CHECK_REGISTRY
                    else "",
                    "target": criterion.target,
                    "weight": criterion.weight,
                    "measured": score_line is not None,
                    "score": _round(score_line.score) if score_line else None,
                    "contribution": _round(score_line.score * criterion.weight) if score_line else None,
                    "evidence_count": len(records),
                    "evidence": _evidence_summary(records),
                }
            )

        recomputed = numerator / denominator if denominator > 0 else None
        engine_raw = line.raw_score if line else None
        total_weight = sum(c.weight for c in pillar.criteria)
        breakdown.append(
            {
                "key": pillar.key,
                # The share of this pillar's criterion weight that had no
                # evidence. It is not scored as zero, so it is scored as
                # nothing -- which is only honest if the share is visible.
                "unmeasured_weight_share": _round(
                    (total_weight - denominator) / total_weight if total_weight > 0 else 0.0, 4
                ),
                "criteria_weight_total": _round(total_weight),
                "name": pillar.name,
                "weight": pillar.weight,
                "scoring_mode": pillar.scoring_mode,
                "core_question": pillar.core_question,
                "rationale": pillar.rationale,
                "criteria": criteria,
                "weighted_numerator": _round(numerator),
                "weight_denominator": _round(denominator),
                # Recomputed here from the criterion lines, then compared with the
                # value the engine wrote: the page proves its own arithmetic.
                "recomputed_raw": _round(recomputed, 4),
                "engine_raw": _round(engine_raw, 4) if engine_raw is not None else None,
                "reconciles": (
                    recomputed is not None
                    and engine_raw is not None
                    and abs(recomputed - engine_raw) < 0.01
                ),
                "score": _round(line.score) if line else None,
                "grade": line.grade if line else None,
                "capped_by": line.capped_by if line else None,
                "cap": caps_by_scope.get(pillar.key),
                "contribution_to_composite": (
                    _round(line.score * pillar.weight)
                    if line and pillar.scoring_mode == "composite"
                    else None
                ),
                "unmeasured_criteria": [c["key"] for c in criteria if not c["measured"]],
            }
        )
    return breakdown


def _composite_breakdown(
    rubric: Rubric,
    scores: list[Score],
    pillars: list[dict[str, Any]],
    caps_by_scope: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    line = next((s for s in scores if s.scope == "composite"), None)
    # Recompute from the engine's own unrounded pillar scores, so a mismatch
    # means a real disagreement rather than a display rounding artefact.
    pillar_lines = {s.key: s for s in scores if s.scope == "pillar"}
    contributing = [
        p for p in pillars if p["scoring_mode"] == "composite" and p["weight"] > 0 and p["score"] is not None
    ]
    numerator = sum(pillar_lines[p["key"]].score * p["weight"] for p in contributing)
    denominator = sum(p["weight"] for p in contributing)
    recomputed = numerator / denominator if denominator > 0 else None
    engine_raw = line.raw_score if line else None
    return {
        "terms": [
            {
                "key": p["key"],
                "name": p["name"],
                "score": p["score"],
                "weight": p["weight"],
                "contribution": _round(pillar_lines[p["key"]].score * p["weight"]),
                "capped_by": p["capped_by"],
            }
            for p in contributing
        ],
        "weighted_numerator": _round(numerator),
        "weight_denominator": _round(denominator),
        "recomputed_raw": _round(recomputed, 4),
        "engine_raw": _round(engine_raw, 4) if engine_raw is not None else None,
        "reconciles": (
            recomputed is not None and engine_raw is not None and abs(recomputed - engine_raw) < 0.01
        ),
        "score": _round(line.score) if line else None,
        "grade": line.grade if line else None,
        "capped_by": line.capped_by if line else None,
        "cap": caps_by_scope.get("composite"),
        "bands": [
            {
                "grade": band.grade,
                "min": band.min_score,
                "max": band.max_score,
                "interpretation": band.interpretation,
            }
            for band in sorted(
                (b for b in rubric.bands if b.scope == "composite"),
                key=lambda b: -b.min_score,
            )
        ],
    }


def _index_breakdown(
    rubric: Rubric,
    scores: list[Score],
    caps_by_scope: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    index_lines = {s.key: s for s in scores if s.scope == "index"}
    dimension_lines = {s.key: s for s in scores if s.scope == "index_dimension"}

    indices = []
    for index_key in sorted({d.index_key for d in rubric.dimensions}):
        line = index_lines.get(index_key)
        dimensions = []
        numerator = denominator = 0.0
        for dimension in sorted(
            (d for d in rubric.dimensions if d.index_key == index_key), key=lambda d: d.key
        ):
            dim_line = dimension_lines.get(f"{index_key}.{dimension.key}")
            if dim_line is not None:
                numerator += dim_line.score * dimension.weight
                denominator += dimension.weight
            dimensions.append(
                {
                    "key": dimension.key,
                    "name": dimension.name,
                    "weight": dimension.weight,
                    "description": dimension.description,
                    "check_ids": list(dimension.check_ids),
                    "score": _round(dim_line.score) if dim_line else None,
                    "contribution": _round(dim_line.score * dimension.weight) if dim_line else None,
                }
            )
        recomputed = numerator / denominator if denominator > 0 else None
        engine_raw = line.raw_score if line else None
        indices.append(
            {
                "key": index_key,
                "name": (rubric.index_names or {}).get(index_key, index_key),
                "dimensions": dimensions,
                "weighted_numerator": _round(numerator),
                "weight_denominator": _round(denominator),
                "recomputed_raw": _round(recomputed, 4),
                "engine_raw": _round(engine_raw, 4) if engine_raw is not None else None,
                "reconciles": (
                    recomputed is not None
                    and engine_raw is not None
                    and abs(recomputed - engine_raw) < 0.01
                ),
                "score": _round(line.score) if line else None,
                "grade": line.grade if line else None,
                "capped_by": line.capped_by if line else None,
                "cap": caps_by_scope.get(index_key),
                "bands": [
                    {
                        "grade": band.grade,
                        "min": band.min_score,
                        "max": band.max_score,
                        "interpretation": band.interpretation,
                    }
                    for band in sorted(
                        (b for b in rubric.bands if b.scope == index_key), key=lambda b: -b.min_score
                    )
                ],
            }
        )
    return indices


# --------------------------------------------------------------------------- #
# what is missing
# --------------------------------------------------------------------------- #


def _coverage(
    rubric: Rubric,
    assessment: Assessment,
    evidence: list[Evidence],
    capabilities: set[str],
    pillars: list[dict[str, Any]],
) -> dict[str, Any]:
    stats = assessment.stats or {}
    criteria_by_key = {c.key: (p, c) for p in rubric.pillars for c in p.criteria}

    unmeasured = []
    for key in stats.get("unmeasured_criteria", []):
        pillar_criterion = criteria_by_key.get(key)
        if pillar_criterion is None:
            unmeasured.append({"key": key, "name": key, "pillar": "", "check_id": "", "why": ""})
            continue
        pillar, criterion = pillar_criterion
        spec = CHECK_REGISTRY.get(criterion.check_id)
        missing = sorted(spec.requires - capabilities) if spec else []
        records = [e for e in evidence if e.check_id == criterion.check_id]

        # Three different absences, and conflating them would mislead: a check
        # that could not run, a check whose evidence is waiting on a human, and
        # a check that ran against an estate with nothing of that kind in it.
        if missing:
            status = "missing_capability"
            why = f"The connector could not observe {', '.join(missing)}, so the check never ran."
        elif records and all(r.status != "accepted" for r in records):
            status = "held_for_review"
            why = (
                f"Measured, but all {len(records)} record(s) sit below the confidence threshold "
                "and are excluded until a reviewer accepts or rejects them."
            )
        else:
            status = "nothing_to_measure"
            why = (
                "The check ran and found nothing of this kind in the harvested estate, so there "
                "is no result to score."
            )

        unmeasured.append(
            {
                "key": key,
                "name": criterion.name,
                "pillar": pillar.name,
                "pillar_key": pillar.key,
                "check_id": criterion.check_id,
                "weight": criterion.weight,
                "missing_capabilities": missing,
                "status": status,
                "evidence_records": len(records),
                "why": why,
            }
        )

    skipped = []
    for check_id in stats.get("checks_skipped", []):
        spec = CHECK_REGISTRY.get(check_id)
        skipped.append(
            {
                "check_id": check_id,
                "title": spec.title if spec else check_id,
                "pillar_key": spec.pillar_key if spec else "",
                "requires": sorted(spec.requires) if spec else [],
                "missing_capabilities": sorted(spec.requires - capabilities) if spec else [],
            }
        )

    pending = [e for e in evidence if e.status == "pending_review"]

    # How much of the composite rests on criteria that produced no evidence.
    # Unmeasured criteria are excluded from their pillar's weighted mean rather
    # than scored as zero, so this is the share of the score that is resting on
    # a smaller base of evidence than the rubric intends.
    scoring = [p for p in pillars if p["scoring_mode"] == "composite" and p["weight"] > 0]
    total_pillar_weight = sum(p["weight"] for p in scoring)
    composite_share = (
        sum(p["weight"] * (p["unmeasured_weight_share"] or 0.0) for p in scoring) / total_pillar_weight
        if total_pillar_weight > 0
        else 0.0
    )

    return {
        "unmeasured_criteria": unmeasured,
        "checks_skipped": skipped,
        "pending_review": [serialize_evidence(e) for e in pending],
        "capabilities_present": sorted(capabilities),
        "capabilities_absent": sorted(
            {req for spec in CHECK_REGISTRY.values() for req in spec.requires} - capabilities
        ),
        "never_collected": list(NEVER_COLLECTED),
        "composite_weight_unmeasured": round(composite_share, 4),
        "by_pillar": [
            {
                "key": p["key"],
                "name": p["name"],
                "unmeasured_weight_share": p["unmeasured_weight_share"],
                "unmeasured_criteria": p["unmeasured_criteria"],
            }
            for p in pillars
            if p["unmeasured_criteria"]
        ],
    }


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def methodology_view(session: Session, assessment: Assessment, rubric: Rubric) -> dict[str, Any]:
    """The full worked example for one snapshot."""
    settings = get_settings()
    tenant = assessment.tenant or session.get(Tenant, assessment.tenant_id)
    scores = list(session.scalars(select(Score).where(Score.assessment_id == assessment.id)))
    evidence = list(session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id)))
    evidence_by_id = {e.id: e for e in evidence if e.id is not None}

    stats = assessment.stats or {}
    triggered = stats.get("blockers_triggered") or stats.get("caps_applied", [])
    caps_by_scope = {cap["scope"]: cap for cap in triggered}
    capabilities = {
        capability
        for entry in assessment.connectors or []
        for capability in (entry.get("stats") or {}).get("capabilities", [])
    }

    pillars = _pillar_breakdown(rubric, scores, evidence_by_id, caps_by_scope)
    accepted = [e for e in evidence if e.status == "accepted"]

    return {
        "assessment": serialize_assessment(assessment),
        "industry": tenant.industry if tenant else None,
        "industry_label": industry_label(tenant.industry) if tenant else None,
        "size_band": tenant.size_band if tenant else None,
        "rubric": {
            "version": rubric.version,
            "name": rubric.name,
            "confidence_threshold": rubric.confidence_threshold,
            "source_digest": rubric.source_digest,
            "index_names": rubric.index_names or {},
        },
        "provenance": _provenance(session, assessment, tenant) if tenant else {},
        "evidence_totals": {
            "records": len(evidence),
            "accepted": len(accepted),
            "pending_review": len([e for e in evidence if e.status == "pending_review"]),
            "rejected": len([e for e in evidence if e.status == "rejected"]),
            "checks_with_evidence": len(
                {e.check_id for e in evidence if not e.check_id.endswith(".by_domain")}
            ),
            "registered_checks": len(CHECK_REGISTRY),
            # Per-domain slices carried for drill-through. They are deliberately
            # excluded from scoring: a domain breakdown is context, not a second
            # vote on the same criterion.
            "context_records": len([e for e in evidence if e.check_id.endswith(".by_domain")]),
            "failing_targets": sum(len(e.failing_targets or []) for e in accepted),
        },
        "pillars": pillars,
        "composite": _composite_breakdown(rubric, scores, pillars, caps_by_scope),
        "indices": _index_breakdown(rubric, scores, caps_by_scope),
        "overrides": [
            {
                "key": o.key,
                "check_id": o.check_id,
                "condition": o.condition,
                "threshold": o.threshold,
                "cap_scope": o.cap_scope,
                "cap_value": o.cap_value,
                "rationale": o.rationale,
                "fired": any(t["override"] == o.key for t in triggered),
                "applied": any(
                    t["override"] == o.key and t.get("applied", True) for t in triggered
                ),
                "failing_targets": next(
                    (t.get("failing_targets") for t in triggered if t["override"] == o.key), None
                ),
            }
            for o in sorted(rubric.overrides, key=lambda o: (o.cap_scope, o.key))
        ],
        "confidence": {
            "threshold": rubric.confidence_threshold,
            "tiers": [
                {**tier, "scored": tier["value"] >= rubric.confidence_threshold}
                for tier in CONFIDENCE_TIERS
            ],
        },
        "coverage": _coverage(rubric, assessment, evidence, capabilities, pillars),
        "settings": {
            "row_sampling_enabled": settings.allow_row_sampling,
        },
    }
