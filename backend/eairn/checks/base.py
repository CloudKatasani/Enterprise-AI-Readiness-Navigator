"""Check library framework.

A check is a pure function of harvested metadata that emits one or more
evidence records. Checks never talk to a customer platform -- by the time they
run, everything they need is in the canonical model. That is what makes a
re-score reproducible.

Every evidence record carries ``{check_id, target, result, confidence,
rationale}``; records below the rubric's confidence threshold are queued for
human review and excluded from scoring until a reviewer accepts them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from eairn.models import (
    AgentAsset,
    Dataset,
    DQIncident,
    DQMonitor,
    GovernanceProgram,
    Grant,
    KPIDefinition,
    LineageEdge,
    MLAsset,
    Policy,
    QuestionnaireResponse,
    RAGCorpus,
    SemanticModel,
    UsageEvent,
)

# Confidence tiers. Anything derived rather than declared is marked down so that
# inferences cannot quietly drive a score (blueprint S1: explainable inferences).
CONFIDENCE_DECLARED = 1.0  # read straight out of a system catalog
CONFIDENCE_RECONCILED = 0.92  # cross-checked between two sources
CONFIDENCE_DERIVED = 0.85  # computed from declared facts (e.g. graph traversal)
CONFIDENCE_INFERRED = 0.70  # heuristic inference -- below threshold by default
CONFIDENCE_SELF_REPORTED = 0.60  # questionnaire answer with no machine backing


@dataclass
class EvidenceRecord:
    check_id: str
    pillar_key: str
    result: float
    rationale: str
    check_title: str = ""
    target_urn: str = "estate"
    target_type: str = "estate"
    platform: str = "cross-platform"
    domain: str | None = None
    measured: dict[str, Any] = field(default_factory=dict)
    confidence: float = CONFIDENCE_DECLARED
    severity: str = "info"
    failing_targets: list[str] = field(default_factory=list)


@dataclass
class CheckSpec:
    check_id: str
    title: str
    pillar_key: str
    requires: frozenset[str]
    func: Callable[["Estate"], Sequence[EvidenceRecord]]
    description: str = ""


REGISTRY: dict[str, CheckSpec] = {}


def check(check_id: str, *, title: str, pillar: str, requires: Iterable[str] = (), description: str = ""):
    """Register a check function under `check_id`."""

    def decorator(func: Callable[["Estate"], Sequence[EvidenceRecord]]):
        if check_id in REGISTRY:
            raise ValueError(f"Duplicate check id {check_id}")
        REGISTRY[check_id] = CheckSpec(
            check_id=check_id,
            title=title,
            pillar_key=pillar,
            requires=frozenset(requires),
            func=func,
            description=description or (func.__doc__ or "").strip(),
        )
        return func

    return decorator


@dataclass
class Estate:
    """Materialised view of one tenant's harvested metadata.

    Checks receive this and nothing else. ``capabilities`` is the union of what
    the connectors in this run could observe; a check whose requirements are not
    met is skipped and reported as not-applicable rather than scored as zero.
    """

    tenant_key: str
    harvested_at: datetime
    datasets: list[Dataset] = field(default_factory=list)
    lineage: list[LineageEdge] = field(default_factory=list)
    policies: list[Policy] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)
    usage: list[UsageEvent] = field(default_factory=list)
    dq_monitors: list[DQMonitor] = field(default_factory=list)
    dq_incidents: list[DQIncident] = field(default_factory=list)
    ml_assets: list[MLAsset] = field(default_factory=list)
    semantic_models: list[SemanticModel] = field(default_factory=list)
    kpi_definitions: list[KPIDefinition] = field(default_factory=list)
    agents: list[AgentAsset] = field(default_factory=list)
    rag_corpora: list[RAGCorpus] = field(default_factory=list)
    governance_programs: list[GovernanceProgram] = field(default_factory=list)
    questionnaire: list[QuestionnaireResponse] = field(default_factory=list)
    capabilities: frozenset[str] = frozenset()
    platforms: tuple[str, ...] = ()

    # -- convenience views --------------------------------------------------- #

    @property
    def tier1(self) -> list[Dataset]:
        return [d for d in self.datasets if d.tier == 1]

    @property
    def all_columns(self):
        for dataset in self.datasets:
            for column in dataset.columns:
                yield dataset, column

    def dataset_by_urn(self, urn: str) -> Dataset | None:
        return self._urn_index.get(urn)

    @property
    def _urn_index(self) -> dict[str, Dataset]:
        cache = getattr(self, "_urn_cache", None)
        if cache is None:
            cache = {d.urn: d for d in self.datasets}
            self._urn_cache = cache
        return cache

    def upstream_of(self, urn: str) -> list[LineageEdge]:
        return [e for e in self.lineage if e.downstream_urn == urn]

    def downstream_of(self, urn: str) -> list[LineageEdge]:
        return [e for e in self.lineage if e.upstream_urn == urn]

    def usage_for(self, urn: str) -> list[UsageEvent]:
        return [u for u in self.usage if u.dataset_urn == urn]

    def monitors_for(self, urn: str) -> list[DQMonitor]:
        return [m for m in self.dq_monitors if m.dataset_urn == urn]

    def questionnaire_answer(self, question_id: str) -> QuestionnaireResponse | None:
        for response in self.questionnaire:
            if response.question_id == question_id:
                return response
        return None

    def domain_of(self, urn: str) -> str | None:
        dataset = self.dataset_by_urn(urn)
        return dataset.domain if dataset else None


def pct(numerator: float, denominator: float) -> float:
    """Percentage, with an empty denominator treated as full marks."""
    if denominator <= 0:
        return 100.0
    return round(100.0 * numerator / denominator, 4)


def severity_for(result: float) -> str:
    if result >= 90:
        return "info"
    if result >= 75:
        return "low"
    if result >= 60:
        return "medium"
    if result >= 40:
        return "high"
    return "critical"


def ratio_evidence(
    spec_id: str,
    pillar: str,
    *,
    title: str,
    numerator: float,
    denominator: float,
    unit: str,
    rationale_template: str,
    failing: Sequence[str] = (),
    confidence: float = CONFIDENCE_DECLARED,
    platform: str = "cross-platform",
    target_urn: str = "estate",
    target_type: str = "estate",
    extra: dict[str, Any] | None = None,
) -> EvidenceRecord:
    """Build an evidence record from a coverage ratio.

    `rationale_template` is formatted with {numerator}, {denominator}, {pct} and
    {unit} so every record explains, in words, exactly what was measured.
    """
    result = pct(numerator, denominator)
    measured = {"numerator": numerator, "denominator": denominator, "unit": unit}
    if extra:
        measured.update(extra)
    rationale = rationale_template.format(
        numerator=_fmt(numerator), denominator=_fmt(denominator), pct=f"{result:.1f}", unit=unit
    )
    failing_list = list(failing)[:200]
    return EvidenceRecord(
        check_id=spec_id,
        check_title=title,
        pillar_key=pillar,
        result=result,
        measured=measured,
        rationale=rationale,
        confidence=confidence,
        severity=severity_for(result),
        failing_targets=failing_list,
        platform=platform,
        target_urn=target_urn,
        target_type=target_type,
    )


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def domain_breakdown(
    spec_id: str,
    pillar: str,
    *,
    title: str,
    buckets: dict[str, tuple[float, float, str]],
    unit: str,
) -> list[EvidenceRecord]:
    """Per-domain context records for the architect heatmap.

    These carry the ``.by_domain`` suffix on their check id so the Scoring
    Engine ignores them -- a domain slice is context for drill-through, not a
    second vote on the same criterion. ``buckets`` maps domain to
    ``(numerator, denominator, platform)``.
    """
    records: list[EvidenceRecord] = []
    for domain, (numerator, denominator, platform) in sorted(buckets.items()):
        if denominator <= 0:
            continue
        result = pct(numerator, denominator)
        records.append(
            EvidenceRecord(
                check_id=f"{spec_id}.by_domain",
                check_title=f"{title} ({domain})",
                pillar_key=pillar,
                result=result,
                measured={"numerator": numerator, "denominator": denominator, "unit": unit},
                rationale=(
                    f"In the {domain} domain, {_fmt(numerator)} of {_fmt(denominator)} {unit} "
                    f"({result:.1f}%) pass this check."
                ),
                severity=severity_for(result),
                platform=platform,
                domain=domain,
                target_urn=f"domain:{domain}",
                target_type="domain",
            )
        )
    return records


def days_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return (end - start).total_seconds() / 86400.0


def run_checks(estate: Estate, check_ids: Iterable[str] | None = None) -> tuple[list[EvidenceRecord], list[str]]:
    """Run the registered checks against an estate.

    Returns ``(evidence, skipped_check_ids)``. A check is skipped when the
    connectors in this run cannot observe what it requires.
    """
    selected = list(check_ids) if check_ids is not None else sorted(REGISTRY)
    evidence: list[EvidenceRecord] = []
    skipped: list[str] = []
    for check_id in selected:
        spec = REGISTRY.get(check_id)
        if spec is None:
            skipped.append(check_id)
            continue
        if not spec.requires.issubset(estate.capabilities):
            skipped.append(check_id)
            continue
        for record in spec.func(estate) or []:
            record.check_title = record.check_title or spec.title
            record.pillar_key = record.pillar_key or spec.pillar_key
            evidence.append(record)
    return evidence, skipped
