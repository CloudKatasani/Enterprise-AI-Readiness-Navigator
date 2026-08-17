"""Recommendation Engine.

Gaps map to playbooks; playbooks are data. For each triggered playbook the
engine runs a what-if simulation through the Scoring Engine -- moving that
playbook's check to its target value and re-scoring -- so the roadmap is ordered
by *simulated composite impact per effort day*, not by intuition.

Every recommendation carries its confidence, its rationale, and the evidence IDs
it was derived from, and lands in ``draft`` status: humans approve and execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import yaml

from eairn.config import SEED_DIR
from eairn.models import Assessment, Evidence, Recommendation, Rubric
from eairn.scoring.engine import ScoringResult, score_assessment
from eairn.scoring.simulate import simulate_uplift

PLAYBOOK_FILE = SEED_DIR / "playbooks.yaml"


@dataclass(frozen=True)
class Playbook:
    id: str
    check_id: str
    title: str
    pillar: str
    horizon: str
    target: float
    trigger: str = "result_below"
    threshold: float = 100.0
    effort_days: float = 10.0
    effort_per_failing_target: float = 0.0
    summary: str = ""
    steps: tuple[str, ...] = ()
    rationale: str = ""
    unblocks: tuple[str, ...] = ()

    def triggered_by(self, result: float) -> bool:
        if self.trigger == "result_below":
            return result < self.threshold
        if self.trigger == "result_at_or_below":
            return result <= self.threshold
        if self.trigger == "always":
            return True
        return False


@dataclass
class PlaybookLibrary:
    version: str
    day_rate: float
    playbooks: list[Playbook] = field(default_factory=list)

    def for_check(self, check_id: str) -> list[Playbook]:
        return [p for p in self.playbooks if p.check_id == check_id]


@lru_cache
def load_playbooks(path: str | None = None) -> PlaybookLibrary:
    file_path = Path(path) if path else PLAYBOOK_FILE
    with file_path.open("r", encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    playbooks = [
        Playbook(
            id=entry["id"],
            check_id=entry["check_id"],
            title=entry["title"],
            pillar=entry["pillar"],
            horizon=entry["horizon"],
            target=float(entry["target"]),
            trigger=entry.get("trigger", "result_below"),
            threshold=float(entry.get("threshold", 100.0)),
            effort_days=float(entry.get("effort_days", 10.0)),
            effort_per_failing_target=float(entry.get("effort_per_failing_target", 0.0)),
            summary=(entry.get("summary") or "").strip(),
            steps=tuple(entry.get("steps", [])),
            rationale=(entry.get("rationale") or "").strip(),
            unblocks=tuple(entry.get("unblocks", [])),
        )
        for entry in spec.get("playbooks", [])
    ]
    return PlaybookLibrary(
        version=str(spec.get("version", "unversioned")),
        day_rate=float(spec.get("day_rate", 0)),
        playbooks=playbooks,
    )


def _aggregate_result(records: Sequence[Evidence]) -> float:
    if not records:
        return 0.0
    return sum(r.result for r in records) / len(records)


def generate_recommendations(
    rubric: Rubric,
    assessment: Assessment,
    evidence: Sequence[Evidence],
    baseline: ScoringResult | None = None,
    *,
    library: PlaybookLibrary | None = None,
) -> list[Recommendation]:
    """Produce draft recommendations, ranked by simulated impact per effort day."""
    library = library or load_playbooks()
    baseline = baseline or score_assessment(rubric, evidence)

    by_check: dict[str, list[Evidence]] = {}
    for record in evidence:
        by_check.setdefault(record.check_id, []).append(record)

    recommendations: list[Recommendation] = []
    for playbook in library.playbooks:
        records = by_check.get(playbook.check_id, [])
        if not records:
            continue
        current = _aggregate_result(records)
        if not playbook.triggered_by(current):
            continue

        uplift = simulate_uplift(rubric, evidence, {playbook.check_id: playbook.target}, baseline=baseline)
        failing_count = sum(len(r.failing_targets or []) for r in records)
        effort = round(playbook.effort_days + playbook.effort_per_failing_target * failing_count, 1)
        # Confidence tracks the evidence the play is founded on: a play built on
        # inferred evidence is itself less certain.
        confidence = round(min(r.confidence for r in records), 4)

        rationale_parts = [playbook.rationale] if playbook.rationale else []
        rationale_parts.append(
            f"Measured {playbook.check_id} at {current:.1f}% against a target of {playbook.target:.0f}%, "
            f"with {failing_count} failing target(s)."
        )
        if uplift.cleared_caps:
            rationale_parts.append(
                "Completing this play releases the hard-blocker cap(s): " + ", ".join(uplift.cleared_caps) + "."
            )
        index_notes = [
            f"{key} {delta:+.1f}" for key, delta in uplift.index_deltas.items() if abs(delta) >= 0.05
        ]
        if index_notes:
            rationale_parts.append("Projected index movement: " + ", ".join(index_notes) + ".")

        recommendations.append(
            Recommendation(
                assessment_id=assessment.id,
                playbook_id=playbook.id,
                title=playbook.title,
                pillar_key=playbook.pillar,
                horizon=playbook.horizon,
                summary=playbook.summary,
                steps=list(playbook.steps),
                effort_days=effort,
                cost_estimate=round(effort * library.day_rate, 2),
                projected_criterion_score=playbook.target,
                composite_impact=round(uplift.composite_delta, 4),
                unblocks=list(playbook.unblocks),
                confidence=confidence,
                rationale=" ".join(rationale_parts),
                evidence_ids=sorted(r.id for r in records if r.id is not None),
                generator="playbook",
                status="draft",
            )
        )

    # Rank by simulated composite impact per effort day; ties break on raw impact.
    recommendations.sort(
        key=lambda r: (r.composite_impact / max(r.effort_days, 0.5), r.composite_impact), reverse=True
    )
    return recommendations


def sequence_roadmap(recommendations: Sequence[Recommendation]) -> list[dict]:
    """Group ranked recommendations into the three delivery horizons.

    Cumulative impact is intentionally additive-with-decay rather than a straight
    sum: plays overlap, so summing simulated deltas would overstate the total.
    """
    horizons = {"quick_win": [], "structural": [], "strategic": []}
    for recommendation in recommendations:
        horizons.setdefault(recommendation.horizon, []).append(recommendation)

    sequenced = []
    cumulative = 0.0
    for horizon, label in (
        ("quick_win", "0-30 days"),
        ("structural", "1-2 quarters"),
        ("strategic", "Strategic"),
    ):
        items = horizons.get(horizon, [])
        if not items:
            continue
        horizon_impact = 0.0
        for position, recommendation in enumerate(items):
            horizon_impact += recommendation.composite_impact * (0.85**position)
        cumulative += horizon_impact
        sequenced.append(
            {
                "horizon": horizon,
                "label": label,
                "recommendations": [r.id for r in items],
                "effort_days": round(sum(r.effort_days for r in items), 1),
                "cost_estimate": round(sum(r.cost_estimate for r in items), 2),
                "projected_impact": round(horizon_impact, 2),
                "cumulative_impact": round(cumulative, 2),
            }
        )
    return sequenced
