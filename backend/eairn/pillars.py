"""Scoring Pillars guide: the teaching view over the rubric.

The methodology view answers *how* a score is computed. This one answers why the
rubric asks these eight questions at all, what an estate looks like when a pillar
is weak, and what a reader gives up by leaving a pillar out of an assessment.

Three sources are merged, and the split matters:

* **The rubric tables** supply structure -- pillar names, weights, core questions,
  criteria, targets and the checks behind them. Nothing here restates a weight or
  a target in prose, so the guide cannot drift from what the engine actually
  applies.
* **`pillar_guide_v*.yaml`** supplies the explanation and the references. It is
  data for the same reason the rubric is: a forked weighting profile carries its
  own teaching material without an engine change.
* **The assessed portfolio** supplies live distribution -- how the estates in
  this instance actually score on each pillar -- so a learner reads the argument
  next to real numbers rather than an assertion.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.checks import REGISTRY as CHECK_REGISTRY
from eairn.config import SEED_DIR
from eairn.models import Assessment, Rubric, Score, Tenant

GUIDE_VERSION = "1"


def guide_path(version: str = GUIDE_VERSION) -> Path:
    return SEED_DIR / f"pillar_guide_v{version}.yaml"


@lru_cache(maxsize=4)
def load_guide(version: str = GUIDE_VERSION) -> dict[str, Any]:
    path = guide_path(version)
    if not path.exists():
        raise FileNotFoundError(f"No pillar guide for version {version} at {path}")
    with path.open("r", encoding="utf-8") as fh:
        guide = yaml.safe_load(fh)
    guide["source_digest"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return guide


def _distribution(session: Session) -> dict[str, list[float]]:
    """Latest complete assessment per tenant -> pillar and index scores.

    A learner asking "does this pillar actually separate estates?" deserves the
    answer from the instance in front of them, not from a claim.
    """
    latest_ids: list[int] = []
    for tenant in session.scalars(select(Tenant)):
        assessment = session.scalar(
            select(Assessment)
            .where(Assessment.tenant_id == tenant.id, Assessment.status == "complete")
            .order_by(Assessment.id.desc())
        )
        if assessment is not None:
            latest_ids.append(assessment.id)
    if not latest_ids:
        return {}

    scores: dict[str, list[float]] = {}
    rows = session.scalars(
        select(Score).where(
            Score.assessment_id.in_(latest_ids), Score.scope.in_(("pillar", "index"))
        )
    )
    for row in rows:
        scores.setdefault(row.key, []).append(row.score)
    return scores


def _summarise(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": round(ordered[0], 1),
        "median": round(ordered[len(ordered) // 2], 1),
        "max": round(ordered[-1], 1),
    }


def _criteria(pillar) -> list[dict[str, Any]]:
    return [
        {
            "key": criterion.key,
            "name": criterion.name,
            "check_id": criterion.check_id,
            "check_title": (
                CHECK_REGISTRY[criterion.check_id].title
                if criterion.check_id in CHECK_REGISTRY
                else criterion.check_id
            ),
            "check_description": (
                CHECK_REGISTRY[criterion.check_id].description
                if criterion.check_id in CHECK_REGISTRY
                else ""
            ),
            "weight": criterion.weight,
            "target": criterion.target,
            "description": criterion.description,
        }
        for criterion in sorted(pillar.criteria, key=lambda c: (-c.weight, c.key))
    ]


def pillar_guide(session: Session, rubric: Rubric) -> dict[str, Any]:
    """The Scoring Pillars view: rubric structure + teaching content + live spread."""
    guide = load_guide()
    content = guide.get("pillars") or {}
    index_content = guide.get("indices") or {}
    distribution = _distribution(session)

    overrides_by_scope: dict[str, list[dict[str, Any]]] = {}
    for override in rubric.overrides:
        overrides_by_scope.setdefault(override.cap_scope, []).append(
            {
                "key": override.key,
                "check_id": override.check_id,
                "condition": override.condition,
                "threshold": override.threshold,
                "cap_value": override.cap_value,
                "rationale": override.rationale,
            }
        )

    pillars = []
    for pillar in sorted(rubric.pillars, key=lambda p: (-p.weight, p.key)):
        teaching = content.get(pillar.key, {})
        pillars.append(
            {
                "key": pillar.key,
                "name": pillar.name,
                # Weight, question and targets come from the rubric, never from
                # the guide: the explanation cannot contradict the arithmetic.
                "weight": pillar.weight,
                "scoring_mode": pillar.scoring_mode,
                "core_question": pillar.core_question,
                "rubric_rationale": pillar.rationale,
                "criteria": _criteria(pillar),
                "overrides": overrides_by_scope.get(pillar.key, []),
                "distribution": _summarise(distribution.get(pillar.key, [])),
                "headline": teaching.get("headline", ""),
                "why_it_matters": teaching.get("why_it_matters", ""),
                "ai_impact": teaching.get("ai_impact", ""),
                "without_it": teaching.get("without_it", []),
                "if_unassessed": teaching.get("if_unassessed", ""),
                "good_looks_like": teaching.get("good_looks_like", []),
                "references": teaching.get("references", []),
            }
        )

    indices = []
    for index_key in sorted({d.index_key for d in rubric.dimensions}):
        teaching = index_content.get(index_key, {})
        indices.append(
            {
                "key": index_key,
                "name": (rubric.index_names or {}).get(index_key, index_key),
                "dimensions": [
                    {
                        "key": d.key,
                        "name": d.name,
                        "weight": d.weight,
                        "description": d.description,
                        "check_ids": list(d.check_ids),
                    }
                    for d in sorted(
                        (d for d in rubric.dimensions if d.index_key == index_key),
                        key=lambda d: d.key,
                    )
                ],
                "overrides": overrides_by_scope.get(index_key, []),
                "distribution": _summarise(distribution.get(index_key, [])),
                "headline": teaching.get("headline", ""),
                "why_it_matters": teaching.get("why_it_matters", ""),
                "if_unassessed": teaching.get("if_unassessed", ""),
            }
        )

    return {
        "guide_version": guide.get("version", GUIDE_VERSION),
        "guide_digest": guide.get("source_digest", ""),
        "rubric": {
            "version": rubric.version,
            "name": rubric.name,
            "confidence_threshold": rubric.confidence_threshold,
        },
        "intro": guide.get("intro", {}),
        "pillars": pillars,
        "indices": indices,
        "grade_bands": [
            {
                "scope": band.scope,
                "grade": band.grade,
                "min": band.min_score,
                "max": band.max_score,
                "interpretation": band.interpretation,
            }
            for band in sorted(rubric.bands, key=lambda b: (b.scope, -b.min_score))
        ],
        "totals": {
            "pillars": len(rubric.pillars),
            "criteria": sum(len(p.criteria) for p in rubric.pillars),
            "registered_checks": len(CHECK_REGISTRY),
            "assessed_organisations": len(distribution.get("data_quality", [])),
        },
    }
