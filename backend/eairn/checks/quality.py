"""Data Quality checks (DQ-xxx).

Scores coverage, effectiveness and operational response -- not tool presence.
"""

from __future__ import annotations

from statistics import median

from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    CONFIDENCE_DERIVED,
    Estate,
    EvidenceRecord,
    check,
    days_between,
    domain_breakdown,
    pct,
    ratio_evidence,
    severity_for,
)

BASELINE_CHECK_TYPES = {"completeness", "freshness", "validity"}
MTTR_TARGET_DAYS = 1.0
MTTR_FLOOR_DAYS = 7.0


@check(
    "DQ-001",
    title="Tier-1 monitor coverage (completeness + freshness + validity)",
    pillar="data_quality",
    requires={"datasets", "dq_monitors"},
)
def tier1_monitor_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Share of Tier-1 datasets carrying all three baseline monitor types."""
    tier1 = estate.tier1
    covered, failing = 0, []
    buckets: dict[str, tuple[float, float, str]] = {}
    for dataset in tier1:
        types = {m.check_type for m in estate.monitors_for(dataset.urn) if m.enabled}
        complete = BASELINE_CHECK_TYPES.issubset(types)
        domain = dataset.domain or "unassigned"
        num, den, _ = buckets.get(domain, (0.0, 0.0, dataset.platform))
        buckets[domain] = (num + (1 if complete else 0), den + 1, dataset.platform)
        if complete:
            covered += 1
        else:
            missing = sorted(BASELINE_CHECK_TYPES - types)
            failing.append(f"{dataset.urn} (missing: {', '.join(missing)})")
    return [
        ratio_evidence(
            "DQ-001",
            "data_quality",
            title="Tier-1 monitor coverage",
            numerator=covered,
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) carry all three baseline monitor "
                "types (completeness, freshness, validity). Datasets missing any baseline type "
                "cannot give an agent a runtime trust signal."
            ),
            failing=failing,
        ),
        *domain_breakdown(
            "DQ-001",
            "data_quality",
            title="Tier-1 monitor coverage",
            buckets=buckets,
            unit="Tier-1 datasets",
        ),
    ]


@check(
    "DQ-002",
    title="DQ rules stored as data",
    pillar="data_quality",
    requires={"dq_monitors"},
)
def rules_as_data(estate: Estate) -> list[EvidenceRecord]:
    """Rules held in rule tables/contracts rather than buried in pipeline code."""
    monitors = estate.dq_monitors
    as_data = [m for m in monitors if m.defined_as_data]
    hardcoded = sorted({m.dataset_urn for m in monitors if not m.defined_as_data})
    return [
        ratio_evidence(
            "DQ-002",
            "data_quality",
            title="DQ rules stored as data",
            numerator=len(as_data),
            denominator=len(monitors),
            unit="DQ rules",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are declared as data (rule tables or "
                "contracts). Rules embedded in pipeline code are neither inventoriable nor "
                "queryable at runtime, so they cannot back a trust signal."
            ),
            failing=hardcoded,
        )
    ]


@check(
    "DQ-003",
    title="Monitor pass-rate",
    pillar="data_quality",
    requires={"dq_monitors"},
)
def monitor_pass_rate(estate: Estate) -> list[EvidenceRecord]:
    """Weighted pass rate across enabled monitors, Tier-1 weighted double."""
    enabled = [m for m in estate.dq_monitors if m.enabled]
    if not enabled:
        return [
            EvidenceRecord(
                check_id="DQ-003",
                pillar_key="data_quality",
                result=0.0,
                measured={"monitors": 0},
                rationale="No enabled DQ monitors were found, so there is no pass-rate signal at all.",
                severity="critical",
            )
        ]
    total_weight = 0.0
    weighted = 0.0
    failing = []
    for monitor in enabled:
        dataset = estate.dataset_by_urn(monitor.dataset_urn)
        weight = 2.0 if dataset and dataset.tier == 1 else 1.0
        total_weight += weight
        weighted += weight * monitor.pass_rate
        if monitor.pass_rate < 0.9:
            failing.append(f"{monitor.dataset_urn}:{monitor.check_type} ({monitor.pass_rate:.0%})")
    result = round(100.0 * weighted / total_weight, 4)
    return [
        EvidenceRecord(
            check_id="DQ-003",
            pillar_key="data_quality",
            result=result,
            measured={"monitors": len(enabled), "weighted_pass_rate": result / 100.0},
            rationale=(
                f"Tier-weighted pass rate across {len(enabled)} enabled monitors is {result:.1f}%. "
                f"{len(failing)} monitor(s) sit below a 90% pass rate."
            ),
            severity=severity_for(result),
            failing_targets=failing[:200],
        )
    ]


@check(
    "DQ-004",
    title="Tier-1 incident MTTR",
    pillar="data_quality",
    requires={"dq_incidents"},
)
def incident_mttr(estate: Estate) -> list[EvidenceRecord]:
    """Median time to resolve Tier-1 incidents, normalised against a 1-day target."""
    tier1_urns = {d.urn for d in estate.tier1}
    durations = []
    unresolved = []
    for incident in estate.dq_incidents:
        if incident.dataset_urn not in tier1_urns:
            continue
        if incident.resolved_at is None:
            unresolved.append(incident.dataset_urn)
            continue
        elapsed = days_between(incident.opened_at, incident.resolved_at)
        if elapsed is not None:
            durations.append(elapsed)
    if not durations and not unresolved:
        return [
            EvidenceRecord(
                check_id="DQ-004",
                pillar_key="data_quality",
                result=100.0,
                measured={"incidents": 0},
                rationale="No Tier-1 data incidents were recorded in the harvest window.",
                confidence=CONFIDENCE_DERIVED,
            )
        ]
    mttr = median(durations) if durations else MTTR_FLOOR_DAYS
    # 100 at or under the 1-day target, 0 at or over the 7-day floor.
    span = MTTR_FLOOR_DAYS - MTTR_TARGET_DAYS
    result = max(0.0, min(100.0, 100.0 * (MTTR_FLOOR_DAYS - mttr) / span))
    penalty = min(25.0, 5.0 * len(unresolved))
    result = round(max(0.0, result - penalty), 4)
    return [
        EvidenceRecord(
            check_id="DQ-004",
            pillar_key="data_quality",
            result=result,
            measured={
                "median_mttr_days": round(mttr, 2),
                "resolved_incidents": len(durations),
                "unresolved_incidents": len(unresolved),
                "target_days": MTTR_TARGET_DAYS,
            },
            rationale=(
                f"Median Tier-1 incident MTTR is {mttr:.1f} days against a {MTTR_TARGET_DAYS:.0f}-day target "
                f"({len(durations)} resolved, {len(unresolved)} still open). Score is normalised "
                f"linearly between the target and a {MTTR_FLOOR_DAYS:.0f}-day floor, with a penalty for open incidents."
            ),
            severity=severity_for(result),
            failing_targets=sorted(set(unresolved)),
        )
    ]


@check(
    "DQ-005",
    title="Incident ownership and closed remediation loops",
    pillar="data_quality",
    requires={"dq_incidents"},
)
def incident_closure(estate: Estate) -> list[EvidenceRecord]:
    """Incidents with a named owner and an evidenced closure."""
    incidents = [i for i in estate.dq_incidents if not i.false_positive]
    closed_and_owned = [i for i in incidents if i.owner and i.resolved_at]
    failing = [i.dataset_urn for i in incidents if not (i.owner and i.resolved_at)]
    return [
        ratio_evidence(
            "DQ-005",
            "data_quality",
            title="Incident ownership and closure",
            numerator=len(closed_and_owned),
            denominator=len(incidents),
            unit="incidents",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have both a named owner and an "
                "evidenced closure. Unowned or open-ended incidents mean the remediation loop "
                "is not closing."
            ),
            failing=sorted(set(failing)),
        )
    ]


@check(
    "DQ-006",
    title="Detection ahead of consumer discovery",
    pillar="data_quality",
    requires={"dq_incidents"},
)
def detection_lead_time(estate: Estate) -> list[EvidenceRecord]:
    """Share of incidents detected by monitoring before a consumer reported them."""
    incidents = [i for i in estate.dq_incidents if not i.false_positive]
    if not incidents:
        return [
            EvidenceRecord(
                check_id="DQ-006",
                pillar_key="data_quality",
                result=100.0,
                measured={"incidents": 0},
                rationale="No incidents in the harvest window; detection lead time is not measurable.",
                confidence=CONFIDENCE_DERIVED,
            )
        ]
    detected_first = []
    consumer_first = []
    for incident in incidents:
        if incident.detected_at is None:
            consumer_first.append(incident.dataset_urn)
        elif incident.consumer_reported_at is None or incident.detected_at <= incident.consumer_reported_at:
            detected_first.append(incident)
        else:
            consumer_first.append(incident.dataset_urn)
    return [
        ratio_evidence(
            "DQ-006",
            "data_quality",
            title="Detection ahead of consumer discovery",
            numerator=len(detected_first),
            denominator=len(incidents),
            unit="incidents",
            rationale_template=(
                "Monitoring detected {numerator} of {denominator} {unit} ({pct}%) before a downstream "
                "consumer reported them. Consumer-first discovery is the failure mode that erodes "
                "trust in AI answers built on the data."
            ),
            failing=sorted(set(consumer_first)),
            confidence=CONFIDENCE_DECLARED,
        )
    ]


@check(
    "DQ-007",
    title="Alert precision",
    pillar="data_quality",
    requires={"dq_incidents"},
)
def alert_precision(estate: Estate) -> list[EvidenceRecord]:
    """Inverse of the false-positive rate: noisy alerting gets ignored."""
    incidents = estate.dq_incidents
    if not incidents:
        return [
            EvidenceRecord(
                check_id="DQ-007",
                pillar_key="data_quality",
                result=100.0,
                measured={"incidents": 0},
                rationale="No alerts fired in the harvest window; precision is not measurable.",
                confidence=CONFIDENCE_DERIVED,
            )
        ]
    true_positives = [i for i in incidents if not i.false_positive]
    result = pct(len(true_positives), len(incidents))
    return [
        EvidenceRecord(
            check_id="DQ-007",
            pillar_key="data_quality",
            result=result,
            measured={"alerts": len(incidents), "false_positives": len(incidents) - len(true_positives)},
            rationale=(
                f"{len(true_positives)} of {len(incidents)} alerts ({result:.1f}%) were genuine. "
                "A noisy monitor estate trains responders to ignore it, which is functionally "
                "equivalent to having no monitoring."
            ),
            severity=severity_for(result),
        )
    ]
