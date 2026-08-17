"""Golden tests for the Scoring Engine.

The blueprint's reproducibility contract: rubric version + evidence set + scores
form an immutable snapshot that can be replayed and defended. These tests assert
the three properties that contract rests on -- determinism, byte-identical
re-scoring, and hard-blocker caps that actually bind.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from eairn.checks import run_checks
from eairn.connectors import build_connector
from eairn.db import session_scope
from eairn.models import Assessment, Evidence, RubricOverride, Score, Tenant
from eairn.pipeline import load_estate, rescore
from eairn.rubric import get_rubric
from eairn.scoring import score_assessment, snapshot_hash


def _snapshot(snapshot_id: str) -> Assessment:
    with session_scope() as session:
        return session.scalar(select(Assessment).where(Assessment.snapshot_id == snapshot_id))


def test_demo_connector_is_deterministic() -> None:
    first = build_connector("demo", {}).harvest()
    second = build_connector("demo", {}).harvest()
    assert first.stats() == second.stats()
    assert [d.urn for d in first.datasets] == [d.urn for d in second.datasets]
    assert [c.protected for d in first.datasets for c in d.columns] == [
        c.protected for d in second.datasets for c in d.columns
    ]


def test_rescore_reproduces_the_snapshot_hash(demo_snapshot: str) -> None:
    with session_scope() as session:
        assessment = session.scalar(
            select(Assessment).where(Assessment.snapshot_id == demo_snapshot)
        )
        recorded = assessment.snapshot_hash
        new_hash, previous = rescore(session, assessment)
    assert previous == recorded
    assert new_hash == recorded, "re-scoring an untouched snapshot must be byte-identical"


def test_scoring_is_pure_and_repeatable(demo_snapshot: str) -> None:
    with session_scope() as session:
        assessment = session.scalar(
            select(Assessment).where(Assessment.snapshot_id == demo_snapshot)
        )
        rubric = get_rubric(session, assessment.rubric_version)
        evidence = list(
            session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id))
        )
        first = score_assessment(rubric, evidence)
        second = score_assessment(rubric, evidence)

    assert first.composite == second.composite
    assert first.pillar_scores() == second.pillar_scores()
    assert snapshot_hash("2.0", evidence, first) == snapshot_hash("2.0", evidence, second)


def test_hard_blockers_cap_their_scope(demo_snapshot: str) -> None:
    """The demo estate is built to trigger all three caps; they must bind."""
    assessment = _snapshot(demo_snapshot)
    applied = {cap["override"] for cap in assessment.stats["caps_applied"]}
    assert "unprotected_classified_columns" in applied
    assert "no_agent_action_audit" in applied
    assert "rag_acl_not_enforced" in applied

    with session_scope() as session:
        scores = {
            s.key: s
            for s in session.scalars(select(Score).where(Score.assessment_id == assessment.id))
        }
    assert scores["security"].score == 49
    assert scores["security"].raw_score > 49, "the cap must be doing work, not matching arithmetic"
    assert scores["agent_readiness"].score == 39
    assert assessment.rri_score == 39


def test_low_confidence_evidence_is_queued_not_scored(demo_snapshot: str) -> None:
    with session_scope() as session:
        assessment = session.scalar(
            select(Assessment).where(Assessment.snapshot_id == demo_snapshot)
        )
        rubric = get_rubric(session, assessment.rubric_version)
        evidence = list(
            session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id))
        )
        pending = [e for e in evidence if e.confidence < rubric.confidence_threshold]
        assert pending, "the demo estate should produce at least one inferred finding"
        assert all(e.status == "pending_review" for e in pending)

        result = score_assessment(rubric, evidence)
        scored_ids = {eid for line in result.lines for eid in line.evidence_ids}
        assert not ({e.id for e in pending} & scored_ids)


def test_reviewer_acceptance_moves_the_score(demo_snapshot: str) -> None:
    from datetime import datetime, timezone

    with session_scope() as session:
        assessment = session.scalar(
            select(Assessment).where(Assessment.snapshot_id == demo_snapshot)
        )
        rubric = get_rubric(session, assessment.rubric_version)
        evidence = list(
            session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id))
        )
        before = score_assessment(rubric, evidence)

        pending = [e for e in evidence if e.status == "pending_review"]
        for record in pending:
            record.status = "accepted"
            record.reviewed_by = "steward@test"
            record.reviewed_at = datetime.now(timezone.utc)
        after = score_assessment(rubric, evidence)

        # Roll the review back so other tests see the original snapshot.
        for record in pending:
            record.status = "pending_review"
            record.reviewed_by = None
            record.reviewed_at = None

    assert after.composite != before.composite


def test_rubric_weights_sum_to_one() -> None:
    with session_scope() as session:
        rubric = get_rubric(session, "2.0")
        composite_weight = sum(p.weight for p in rubric.pillars if p.scoring_mode == "composite")
    assert composite_weight == pytest.approx(1.0)


def test_every_criterion_maps_to_a_registered_check() -> None:
    from eairn.checks import REGISTRY

    with session_scope() as session:
        rubric = get_rubric(session, "2.0")
        missing = [
            (p.key, c.key, c.check_id)
            for p in rubric.pillars
            for c in p.criteria
            if c.check_id not in REGISTRY
        ]
        dimension_missing = [
            (d.index_key, d.key, check_id)
            for d in rubric.dimensions
            for check_id in d.check_ids
            if check_id not in REGISTRY
        ]
    assert not missing, f"rubric references unregistered checks: {missing}"
    assert not dimension_missing, f"index dimensions reference unregistered checks: {dimension_missing}"


def test_overrides_reference_registered_checks() -> None:
    from eairn.checks import REGISTRY

    with session_scope() as session:
        overrides = list(session.scalars(select(RubricOverride)))
    assert overrides
    assert all(o.check_id in REGISTRY for o in overrides)


def test_checks_skipped_when_capability_absent(demo_tenant_key: str) -> None:
    """A check whose evidence source is unavailable is skipped, never scored zero."""
    from datetime import datetime, timezone

    with session_scope() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.key == demo_tenant_key))
        estate = load_estate(
            session,
            tenant,
            capabilities={"datasets", "columns", "descriptions"},
            harvested_at=datetime.now(timezone.utc),
        )
        _, skipped = run_checks(estate)

    assert "RG-005" in skipped, "RAG checks require rag_corpora and must be skipped without it"
    assert "AG-006" in skipped, "agent checks require agent evidence and must be skipped without it"
