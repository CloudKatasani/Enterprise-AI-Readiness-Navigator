"""Action plan: what to fix, who fixes it, and what it is worth.

The three role views answer "where do we stand". This module answers the
question a demo audience asks next -- *what do we actually do on Monday* -- and
it answers it only from evidence already in the snapshot:

* **Blockers** first, because a cap bounds the grade no matter what else moves.
* **Architect actions** are criteria measured below their rubric target, ranked
  by what closing them is worth: pillar weight x criterion weight x the distance
  from target. No judgement is added; the ranking is arithmetic over the rubric.
* **Steward actions** are the two queues a human owns -- evidence held below the
  confidence threshold, and accepted findings with failing objects to work
  through.
* **Guidance** is the sequenced roadmap the Recommendation Engine already
  produced, whose impact was measured by re-running the scoring engine rather
  than estimated.

Nothing here invents an action. Every row carries the check that produced it and
the objects that failed, so "fix this" can always be resolved to "fix these".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.checks import REGISTRY as CHECK_REGISTRY
from eairn.dashboard import SEVERITY_ORDER, serialize_assessment, serialize_recommendation
from eairn.models import Assessment, Evidence, Recommendation, Rubric, Score
from eairn.recommend.engine import load_playbooks, sequence_roadmap
from eairn.rubric import grade_for

#: How many objects to show per action. The full list stays in the steward view;
#: an action plan is a work list, not a data dump.
SAMPLE_TARGETS = 5


def _criterion_index(rubric: Rubric) -> dict[str, Any]:
    return {
        criterion.key: (pillar, criterion)
        for pillar in rubric.pillars
        for criterion in pillar.criteria
    }


def action_plan(session: Session, assessment: Assessment, rubric: Rubric) -> dict[str, Any]:
    scores = list(session.scalars(select(Score).where(Score.assessment_id == assessment.id)))
    evidence = list(session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id)))
    recommendations = list(
        session.scalars(select(Recommendation).where(Recommendation.assessment_id == assessment.id))
    )
    evidence_by_check: dict[str, list[Evidence]] = {}
    for record in evidence:
        evidence_by_check.setdefault(record.check_id, []).append(record)

    criteria = _criterion_index(rubric)
    pillar_lines = {s.key: s for s in scores if s.scope == "pillar"}
    stats = assessment.stats or {}
    triggered = stats.get("blockers_triggered") or stats.get("caps_applied", [])
    # A recommendation names its playbook; the playbook names the check it
    # targets. Resolving through the library keeps the mapping in one place.
    check_by_playbook = {play.id: play.check_id for play in load_playbooks().playbooks}
    plays_by_check: dict[str, list[Recommendation]] = {}
    for rec in recommendations:
        check_id = check_by_playbook.get(rec.playbook_id)
        if check_id:
            plays_by_check.setdefault(check_id, []).append(rec)

    # -- blockers ---------------------------------------------------------- #
    blockers = []
    for cap in triggered:
        records = evidence_by_check.get(cap["check_id"], [])
        failing = [t for record in records for t in (record.failing_targets or [])]
        plays = plays_by_check.get(cap["check_id"], [])
        blockers.append(
            {
                **cap,
                "check_title": records[0].check_title if records else cap["check_id"],
                "current_result": round(records[0].result, 2) if records else None,
                "failing_sample": failing[:SAMPLE_TARGETS],
                "failing_total": len(failing),
                "plays": [serialize_recommendation(p) for p in plays],
                "owner": "Architect",
            }
        )
    blockers.sort(key=lambda b: (not b.get("applied", True), -b["failing_targets"]))

    # -- architect actions -------------------------------------------------- #
    architect: list[dict[str, Any]] = []
    for line in (s for s in scores if s.scope == "criterion"):
        entry = criteria.get(line.key)
        if entry is None:
            continue
        pillar, criterion = entry
        target = criterion.target
        if target is None or line.score >= target:
            continue
        records = evidence_by_check.get(criterion.check_id, [])
        failing = [t for record in records for t in (record.failing_targets or [])]
        shortfall = round(target - line.score, 2)
        architect.append(
            {
                "kind": "below_target",
                "criterion_key": line.key,
                "criterion": criterion.name,
                "pillar_key": pillar.key,
                "pillar": pillar.name,
                "check_id": criterion.check_id,
                "check_description": (
                    CHECK_REGISTRY[criterion.check_id].description
                    if criterion.check_id in CHECK_REGISTRY
                    else ""
                ),
                "score": round(line.score, 2),
                "target": target,
                "shortfall": shortfall,
                # What closing this criterion is worth, in composite terms:
                # the rubric's own weights, not an opinion about difficulty.
                "priority": round(
                    pillar.weight * (criterion.weight / max(sum(c.weight for c in pillar.criteria), 1))
                    * shortfall,
                    4,
                ),
                "pillar_capped_by": pillar_lines[pillar.key].capped_by if pillar.key in pillar_lines else None,
                "failing_total": len(failing),
                "failing_sample": failing[:SAMPLE_TARGETS],
                "plays": [serialize_recommendation(p) for p in plays_by_check.get(criterion.check_id, [])],
                "owner": "Architect",
            }
        )

    # Coverage gaps are architect work too: closing them needs connector or
    # platform change, not a steward decision.
    for check_id in stats.get("checks_skipped", []):
        spec = CHECK_REGISTRY.get(check_id)
        architect.append(
            {
                "kind": "no_coverage",
                "criterion_key": check_id,
                "criterion": spec.title if spec else check_id,
                "pillar_key": spec.pillar_key if spec else "",
                "pillar": (spec.pillar_key if spec else "").replace("_", " ").title(),
                "check_id": check_id,
                "check_description": spec.description if spec else "",
                "score": None,
                "target": None,
                "shortfall": None,
                "priority": 0.0,
                "requires": sorted(spec.requires) if spec else [],
                "failing_total": 0,
                "failing_sample": [],
                "plays": [],
                "owner": "Architect",
            }
        )

    architect.sort(key=lambda a: (-(a["priority"] or 0), a["criterion_key"]))

    # -- steward actions ---------------------------------------------------- #
    steward: list[dict[str, Any]] = []
    for record in evidence:
        if record.status != "pending_review":
            continue
        steward.append(
            {
                "kind": "decide",
                "evidence_id": record.id,
                "check_id": record.check_id,
                "check_title": record.check_title,
                "pillar_key": record.pillar_key,
                "result": round(record.result, 2),
                "confidence": round(record.confidence, 2),
                "rationale": record.rationale,
                "failing_total": len(record.failing_targets or []),
                "failing_sample": (record.failing_targets or [])[:SAMPLE_TARGETS],
                "owner": "Steward",
                "action": (
                    "Confirm or reject this inference. It is excluded from the score until "
                    "someone decides, and accepting it re-scores the snapshot."
                ),
            }
        )

    findings = sorted(
        (e for e in evidence if e.status == "accepted" and e.failing_targets),
        key=lambda e: (SEVERITY_ORDER.get(e.severity, 9), -len(e.failing_targets or [])),
    )
    for record in findings[:12]:
        steward.append(
            {
                "kind": "remediate",
                "evidence_id": record.id,
                "check_id": record.check_id,
                "check_title": record.check_title,
                "pillar_key": record.pillar_key,
                "severity": record.severity,
                "result": round(record.result, 2),
                "confidence": round(record.confidence, 2),
                "rationale": record.rationale,
                "failing_total": len(record.failing_targets or []),
                "failing_sample": (record.failing_targets or [])[:SAMPLE_TARGETS],
                "owner": "Steward",
                "action": (
                    f"Work the {len(record.failing_targets or [])} failing object(s) with their "
                    "owners; each one is named in the steward view."
                ),
            }
        )

    # -- guidance ----------------------------------------------------------- #
    ranked = sorted(recommendations, key=lambda r: -r.composite_impact)
    roadmap = sequence_roadmap(ranked)
    baseline = assessment.composite_score or 0.0
    horizons = []
    for horizon in roadmap:
        projected = round(baseline + horizon["cumulative_impact"], 2)
        horizons.append(
            {
                **horizon,
                "projected_composite": projected,
                "projected_grade": grade_for(rubric, "composite", projected)[0],
                "recommendations": [
                    serialize_recommendation(r) for r in ranked if r.id in set(horizon["recommendations"])
                ],
            }
        )

    projected_total = round(baseline + sum(h["projected_impact"] for h in roadmap), 2)
    return {
        "assessment": serialize_assessment(assessment),
        "blockers": blockers,
        "architect_actions": architect,
        "steward_actions": steward,
        "horizons": horizons,
        "projection": {
            "current_composite": round(baseline, 2),
            "current_grade": assessment.grade,
            "projected_composite": projected_total,
            "projected_grade": grade_for(rubric, "composite", projected_total)[0],
            "total_effort_days": round(sum(r.effort_days for r in recommendations), 1),
            "total_cost_estimate": round(sum(r.cost_estimate for r in recommendations), 2),
        },
        "summary": {
            "blockers": len(blockers),
            "blockers_binding": len([b for b in blockers if b.get("applied", True)]),
            "architect_actions": len(architect),
            "architect_below_target": len([a for a in architect if a["kind"] == "below_target"]),
            "coverage_gaps": len([a for a in architect if a["kind"] == "no_coverage"]),
            "steward_decisions": len([s for s in steward if s["kind"] == "decide"]),
            "steward_remediations": len([s for s in steward if s["kind"] == "remediate"]),
            "failing_objects": sum(len(e.failing_targets or []) for e in findings),
        },
    }
