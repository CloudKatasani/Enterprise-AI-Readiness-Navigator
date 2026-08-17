"""Rubric loading: YAML on disk -> versioned rows in the rubric_* tables.

The Scoring Engine never reads YAML. It reads the tables this module populates,
which is what makes an assessment replayable: the rubric it scored under is
persisted alongside its evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.config import SEED_DIR
from eairn.models import (
    Rubric,
    RubricCriterion,
    RubricGradeBand,
    RubricIndexDimension,
    RubricOverride,
    RubricPillar,
)


def rubric_path(version: str) -> Path:
    return SEED_DIR / f"rubric_v{version}.yaml"


def load_rubric_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_rubric(session: Session, version: str) -> Rubric | None:
    return session.scalar(select(Rubric).where(Rubric.version == version))


def install_rubric(session: Session, version: str, *, replace: bool = False) -> Rubric:
    """Load rubric `version` from YAML into the database.

    Idempotent: an already-installed rubric with a matching source digest is
    returned untouched. A changed digest is refused unless `replace=True`,
    because silently mutating a rubric would break the reproducibility contract
    for assessments already scored against it.
    """
    path = rubric_path(version)
    if not path.exists():
        raise FileNotFoundError(f"No rubric file for version {version} at {path}")

    spec = load_rubric_file(path)
    if str(spec.get("version")) != str(version):
        raise ValueError(f"Rubric file {path} declares version {spec.get('version')!r}, expected {version!r}")

    source_digest = digest_of(path)
    existing = get_rubric(session, version)
    if existing is not None:
        if existing.source_digest == source_digest and not replace:
            return existing
        if not replace:
            raise ValueError(
                f"Rubric {version} is installed with a different source digest. "
                "Bump the version, or pass replace=True if no assessment has used it."
            )
        session.delete(existing)
        session.flush()

    rubric = Rubric(
        version=version,
        name=spec.get("name", f"Rubric {version}"),
        confidence_threshold=float(spec.get("confidence_threshold", 0.80)),
        source_digest=source_digest,
    )
    session.add(rubric)
    session.flush()

    for pillar_spec in spec.get("pillars", []):
        pillar = RubricPillar(
            rubric_id=rubric.id,
            key=pillar_spec["key"],
            name=pillar_spec["name"],
            core_question=pillar_spec.get("core_question", ""),
            weight=float(pillar_spec.get("weight", 0.0)),
            scoring_mode=pillar_spec.get("scoring_mode", "composite"),
            rationale=pillar_spec.get("rationale", ""),
        )
        session.add(pillar)
        session.flush()
        for criterion_spec in pillar_spec.get("criteria", []):
            session.add(
                RubricCriterion(
                    pillar_id=pillar.id,
                    key=criterion_spec["key"],
                    name=criterion_spec["name"],
                    check_id=criterion_spec["check_id"],
                    weight=float(criterion_spec.get("weight", 1.0)),
                    target=criterion_spec.get("target"),
                    description=criterion_spec.get("description", ""),
                )
            )

    for override_spec in spec.get("overrides", []):
        session.add(
            RubricOverride(
                rubric_id=rubric.id,
                key=override_spec["key"],
                check_id=override_spec["check_id"],
                condition=override_spec["condition"],
                threshold=float(override_spec["threshold"]),
                cap_scope=override_spec["cap_scope"],
                cap_value=float(override_spec["cap_value"]),
                rationale=override_spec.get("rationale", "").strip(),
            )
        )

    for index_key, index_spec in (spec.get("indices") or {}).items():
        for dimension_spec in index_spec.get("dimensions", []):
            session.add(
                RubricIndexDimension(
                    rubric_id=rubric.id,
                    index_key=index_key,
                    key=dimension_spec["key"],
                    name=dimension_spec["name"],
                    weight=float(dimension_spec.get("weight", 1.0)),
                    description=dimension_spec.get("description", ""),
                    check_ids=list(dimension_spec.get("check_ids", [])),
                )
            )

    for scope, bands in (spec.get("grade_bands") or {}).items():
        for band in bands:
            session.add(
                RubricGradeBand(
                    rubric_id=rubric.id,
                    scope=scope,
                    min_score=float(band["min"]),
                    max_score=float(band["max"]),
                    grade=band["grade"],
                    interpretation=band.get("interpretation", ""),
                )
            )

    session.flush()
    return rubric


def grade_for(rubric: Rubric, scope: str, score: float) -> tuple[str, str]:
    """Return (grade, interpretation) for a score under a rubric's bands."""
    candidates = [b for b in rubric.bands if b.scope == scope]
    if not candidates:
        candidates = [b for b in rubric.bands if b.scope == "composite"]
    for band in sorted(candidates, key=lambda b: b.min_score, reverse=True):
        if score >= band.min_score:
            return band.grade, band.interpretation
    return "unscored", ""
