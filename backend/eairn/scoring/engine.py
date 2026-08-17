"""Scoring Engine.

Applies a versioned rubric to a set of evidence records and produces criterion,
pillar, composite and index scores plus grades. Three invariants:

* Rubric criteria, weights, bands and overrides come from the rubric tables --
  the engine contains no readiness opinion of its own.
* Evidence below the rubric's confidence threshold is excluded from scoring and
  queued for human review; it never silently moves a number.
* Given the same rubric version and the same evidence, the engine produces the
  same scores and the same snapshot hash, every time.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from eairn.models import Assessment, Evidence, Rubric, Score
from eairn.rubric import grade_for

STATUS_ACCEPTED = "accepted"
STATUS_PENDING = "pending_review"
STATUS_REJECTED = "rejected"


@dataclass
class ScoreLine:
    scope: str
    key: str
    name: str
    score: float
    raw_score: float
    weight: float = 0.0
    parent_key: str | None = None
    grade: str | None = None
    capped_by: str | None = None
    evidence_ids: list[int] = field(default_factory=list)


@dataclass
class ScoringResult:
    composite: float | None
    grade: str | None
    interpretation: str = ""
    lines: list[ScoreLine] = field(default_factory=list)
    indices: dict[str, float] = field(default_factory=dict)
    index_grades: dict[str, str] = field(default_factory=dict)
    caps_applied: list[dict] = field(default_factory=list)
    unmeasured_criteria: list[str] = field(default_factory=list)
    pending_review_evidence: list[int] = field(default_factory=list)

    def pillar_scores(self) -> dict[str, float]:
        return {line.key: line.score for line in self.lines if line.scope == "pillar"}

    def criterion_scores(self) -> dict[str, float]:
        return {line.key: line.score for line in self.lines if line.scope == "criterion"}


def classify_evidence(evidence: Evidence, threshold: float) -> str:
    """Reviewer decisions win; otherwise confidence decides."""
    if evidence.reviewed_at is not None and evidence.status in {STATUS_ACCEPTED, STATUS_REJECTED}:
        return evidence.status
    return STATUS_ACCEPTED if evidence.confidence >= threshold else STATUS_PENDING


def _evidence_weight(evidence: Evidence) -> float:
    """Aggregate multiple records for one check by measurement size."""
    denominator = (evidence.measured or {}).get("denominator")
    try:
        value = float(denominator)
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def _aggregate(records: Sequence[Evidence]) -> float:
    total_weight = sum(_evidence_weight(r) for r in records)
    if total_weight <= 0:
        return 0.0
    return sum(r.result * _evidence_weight(r) for r in records) / total_weight


def _failing_count(records: Iterable[Evidence]) -> int:
    return sum(len(r.failing_targets or []) for r in records)


def score_assessment(rubric: Rubric, evidence: Sequence[Evidence]) -> ScoringResult:
    """Score a set of evidence records against a rubric. Pure: no I/O."""
    threshold = rubric.confidence_threshold
    by_check: dict[str, list[Evidence]] = defaultdict(list)
    pending: list[int] = []
    for record in evidence:
        status = classify_evidence(record, threshold)
        record.status = status
        if status == STATUS_ACCEPTED:
            by_check[record.check_id].append(record)
        elif status == STATUS_PENDING and record.id is not None:
            pending.append(record.id)

    lines: list[ScoreLine] = []
    unmeasured: list[str] = []
    caps: list[dict] = []
    overrides_by_scope: dict[str, list] = defaultdict(list)
    for override in rubric.overrides:
        overrides_by_scope[override.cap_scope].append(override)

    def cap_for(scope: str, raw: float) -> tuple[float, str | None]:
        """Apply the strictest triggered hard-blocker override for a scope."""
        best_value, best_key = raw, None
        for override in overrides_by_scope.get(scope, []):
            records = by_check.get(override.check_id, [])
            if not records:
                continue
            triggered = False
            if override.condition == "failing_targets_above":
                triggered = _failing_count(records) > override.threshold
            elif override.condition == "result_below":
                triggered = _aggregate(records) < override.threshold
            elif override.condition == "result_at_or_below":
                triggered = _aggregate(records) <= override.threshold
            if triggered and override.cap_value < best_value:
                best_value, best_key = override.cap_value, override.key
                caps.append(
                    {
                        "override": override.key,
                        "scope": scope,
                        "check_id": override.check_id,
                        "cap_value": override.cap_value,
                        "uncapped_score": round(raw, 4),
                        "rationale": override.rationale,
                        "failing_targets": _failing_count(records),
                    }
                )
        return best_value, best_key

    # -- criteria and pillars ------------------------------------------------ #
    composite_numerator = composite_denominator = 0.0
    for pillar in sorted(rubric.pillars, key=lambda p: p.key):
        pillar_numerator = pillar_denominator = 0.0
        pillar_evidence: list[int] = []
        for criterion in sorted(pillar.criteria, key=lambda c: c.key):
            records = by_check.get(criterion.check_id, [])
            if not records:
                unmeasured.append(criterion.key)
                continue
            value = _aggregate(records)
            ids = [r.id for r in records if r.id is not None]
            pillar_evidence.extend(ids)
            lines.append(
                ScoreLine(
                    scope="criterion",
                    key=criterion.key,
                    parent_key=pillar.key,
                    name=criterion.name,
                    score=round(value, 4),
                    raw_score=round(value, 4),
                    weight=criterion.weight,
                    evidence_ids=ids,
                )
            )
            pillar_numerator += value * criterion.weight
            pillar_denominator += criterion.weight

        if pillar_denominator <= 0:
            continue
        raw = pillar_numerator / pillar_denominator
        capped, capped_by = cap_for(pillar.key, raw)
        lines.append(
            ScoreLine(
                scope="pillar",
                key=pillar.key,
                name=pillar.name,
                score=round(capped, 4),
                raw_score=round(raw, 4),
                weight=pillar.weight,
                capped_by=capped_by,
                evidence_ids=pillar_evidence,
                grade=grade_for(rubric, "composite", capped)[0],
            )
        )
        if pillar.scoring_mode == "composite" and pillar.weight > 0:
            composite_numerator += capped * pillar.weight
            composite_denominator += pillar.weight

    composite = None
    grade = interpretation = ""
    if composite_denominator > 0:
        raw_composite = composite_numerator / composite_denominator
        composite, composite_capped_by = cap_for("composite", raw_composite)
        composite = round(composite, 4)
        grade, interpretation = grade_for(rubric, "composite", composite)
        lines.append(
            ScoreLine(
                scope="composite",
                key="composite",
                name="Composite readiness",
                score=composite,
                raw_score=round(raw_composite, 4),
                weight=1.0,
                grade=grade,
                capped_by=composite_capped_by,
            )
        )

    # -- overlay indices (ARI, RRI) ------------------------------------------ #
    indices: dict[str, float] = {}
    index_grades: dict[str, str] = {}
    dimensions_by_index: dict[str, list] = defaultdict(list)
    for dimension in rubric.dimensions:
        dimensions_by_index[dimension.index_key].append(dimension)

    for index_key, dimensions in sorted(dimensions_by_index.items()):
        numerator = denominator = 0.0
        for dimension in sorted(dimensions, key=lambda d: d.key):
            values, ids = [], []
            for check_id in dimension.check_ids:
                records = by_check.get(check_id, [])
                if not records:
                    continue
                values.append(_aggregate(records))
                ids.extend(r.id for r in records if r.id is not None)
            if not values:
                continue
            dimension_score = sum(values) / len(values)
            lines.append(
                ScoreLine(
                    scope="index_dimension",
                    key=f"{index_key}.{dimension.key}",
                    parent_key=index_key,
                    name=dimension.name,
                    score=round(dimension_score, 4),
                    raw_score=round(dimension_score, 4),
                    weight=dimension.weight,
                    evidence_ids=ids,
                )
            )
            numerator += dimension_score * dimension.weight
            denominator += dimension.weight
        if denominator <= 0:
            continue
        raw_index = numerator / denominator
        index_score, capped_by = cap_for(index_key, raw_index)
        index_score = round(index_score, 4)
        index_grade, _ = grade_for(rubric, index_key, index_score)
        indices[index_key] = index_score
        index_grades[index_key] = index_grade
        lines.append(
            ScoreLine(
                scope="index",
                key=index_key,
                name=index_key,
                score=index_score,
                raw_score=round(raw_index, 4),
                weight=1.0,
                grade=index_grade,
                capped_by=capped_by,
            )
        )

    return ScoringResult(
        composite=composite,
        grade=grade or None,
        interpretation=interpretation,
        lines=lines,
        indices=indices,
        index_grades=index_grades,
        caps_applied=caps,
        unmeasured_criteria=sorted(set(unmeasured)),
        pending_review_evidence=pending,
    )


def persist_scores(assessment: Assessment, result: ScoringResult) -> list[Score]:
    """Materialise score lines as rows attached to an assessment."""
    rows = [
        Score(
            assessment_id=assessment.id,
            scope=line.scope,
            key=line.key,
            parent_key=line.parent_key,
            name=line.name,
            score=line.score,
            raw_score=line.raw_score,
            weight=line.weight,
            grade=line.grade,
            capped_by=line.capped_by,
            evidence_ids=sorted(line.evidence_ids),
        )
        for line in result.lines
    ]
    assessment.composite_score = result.composite
    assessment.grade = result.grade
    assessment.ari_score = result.indices.get("ARI")
    assessment.ari_grade = result.index_grades.get("ARI")
    assessment.rri_score = result.indices.get("RRI")
    assessment.rri_grade = result.index_grades.get("RRI")
    return rows


def snapshot_hash(rubric_version: str, evidence: Sequence[Evidence], result: ScoringResult) -> str:
    """Stable digest over {rubric version + evidence + scores}.

    This is the reproducibility key: replaying an assessment against the same
    rubric and evidence must reproduce this hash exactly.
    """
    evidence_payload = sorted(
        (
            record.check_id,
            record.target_urn,
            round(record.result, 6),
            round(record.confidence, 6),
            record.status,
            tuple(sorted(record.failing_targets or [])),
        )
        for record in evidence
    )
    score_payload = sorted(
        (line.scope, line.key, round(line.score, 6), round(line.raw_score, 6), line.capped_by or "")
        for line in result.lines
    )
    blob = json.dumps(
        {"rubric_version": rubric_version, "evidence": evidence_payload, "scores": score_payload},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
