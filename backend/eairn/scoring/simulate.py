"""What-if simulation.

"Fix governance" is not a roadmap. This module answers the question a CDO
actually asks -- *if we do this specific thing, what does the score become?* --
by re-running the scoring engine over a copy of the evidence with named checks
moved to a target value.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Mapping, Sequence

from eairn.models import Evidence, Rubric
from eairn.scoring.engine import ScoringResult, score_assessment


@dataclass
class Uplift:
    baseline_composite: float | None
    projected_composite: float | None
    composite_delta: float
    baseline_indices: dict[str, float]
    projected_indices: dict[str, float]
    index_deltas: dict[str, float]
    baseline_grade: str | None = None
    projected_grade: str | None = None
    cleared_caps: list[str] = None  # type: ignore[assignment]

    def as_dict(self) -> dict:
        return {
            "baseline_composite": self.baseline_composite,
            "projected_composite": self.projected_composite,
            "composite_delta": round(self.composite_delta, 4),
            "baseline_grade": self.baseline_grade,
            "projected_grade": self.projected_grade,
            "baseline_indices": self.baseline_indices,
            "projected_indices": self.projected_indices,
            "index_deltas": {k: round(v, 4) for k, v in self.index_deltas.items()},
            "cleared_caps": self.cleared_caps or [],
        }


def _clone_evidence(records: Sequence[Evidence]) -> list[Evidence]:
    """Detached copies so a simulation cannot touch persisted evidence."""
    clones = []
    for record in records:
        clone = Evidence(
            check_id=record.check_id,
            check_title=record.check_title,
            pillar_key=record.pillar_key,
            platform=record.platform,
            domain=record.domain,
            target_urn=record.target_urn,
            target_type=record.target_type,
            result=record.result,
            measured=copy.deepcopy(record.measured or {}),
            confidence=record.confidence,
            rationale=record.rationale,
            severity=record.severity,
            status=record.status,
            failing_targets=list(record.failing_targets or []),
            reviewed_by=record.reviewed_by,
            reviewed_at=record.reviewed_at,
        )
        clone.id = record.id
        clones.append(clone)
    return clones


def simulate_uplift(
    rubric: Rubric,
    evidence: Sequence[Evidence],
    targets: Mapping[str, float],
    *,
    baseline: ScoringResult | None = None,
) -> Uplift:
    """Move each ``check_id`` in `targets` to its target value and re-score.

    Reaching a target of 100 also clears that check's failing targets, which is
    what releases any hard-blocker cap the check was triggering -- so the
    simulation reflects cap relief, not just arithmetic.
    """
    base = baseline or score_assessment(rubric, _clone_evidence(evidence))
    projected_evidence = _clone_evidence(evidence)
    for record in projected_evidence:
        target = targets.get(record.check_id)
        if target is None:
            continue
        record.result = max(record.result, float(target))
        if record.result >= 100:
            record.failing_targets = []
        elif record.failing_targets:
            # Keep the residual share of failures implied by the target value.
            keep = max(0, int(round(len(record.failing_targets) * (100 - record.result) / 100)))
            record.failing_targets = record.failing_targets[:keep]
        # A remediation that lands is observed, not inferred.
        record.confidence = max(record.confidence, rubric.confidence_threshold)

    projected = score_assessment(rubric, projected_evidence)
    baseline_caps = {cap["override"] for cap in base.caps_applied}
    projected_caps = {cap["override"] for cap in projected.caps_applied}
    return Uplift(
        baseline_composite=base.composite,
        projected_composite=projected.composite,
        composite_delta=(projected.composite or 0.0) - (base.composite or 0.0),
        baseline_indices=dict(base.indices),
        projected_indices=dict(projected.indices),
        index_deltas={
            key: projected.indices.get(key, 0.0) - base.indices.get(key, 0.0)
            for key in set(base.indices) | set(projected.indices)
        },
        baseline_grade=base.grade,
        projected_grade=projected.grade,
        cleared_caps=sorted(baseline_caps - projected_caps),
    )
