"""Governance checks (GV-xxx).

The governance tool is both an evidence source and a scored subject: EAIRN asks
whether the programme is operationally alive, not whether a tool was bought.
"""

from __future__ import annotations

from datetime import timedelta

from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    CONFIDENCE_DERIVED,
    CONFIDENCE_RECONCILED,
    Estate,
    EvidenceRecord,
    check,
    domain_breakdown,
    pct,
    ratio_evidence,
    severity_for,
)

OWNER_VERIFICATION_WINDOW_DAYS = 365
STEWARD_LATENCY_TARGET_HOURS = 48.0
STEWARD_LATENCY_FLOOR_HOURS = 240.0
TOP_QUERIED_SAMPLE = 25


@check("GV-001", title="Tier-1 owner coverage", pillar="governance", requires={"datasets"})
def tier1_owner_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Tier-1 datasets with a named, accountable owner."""
    tier1 = estate.tier1
    owned = [d for d in tier1 if d.owner]
    failing = [d.urn for d in tier1 if not d.owner]
    buckets: dict[str, tuple[float, float, str]] = {}
    for dataset in tier1:
        domain = dataset.domain or "unassigned"
        num, den, _ = buckets.get(domain, (0.0, 0.0, dataset.platform))
        buckets[domain] = (num + (1 if dataset.owner else 0), den + 1, dataset.platform)
    return [
        ratio_evidence(
            "GV-001",
            "governance",
            title="Tier-1 owner coverage",
            numerator=len(owned),
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have a named owner. Ownership is the "
                "routing address for every finding an agent or a steward raises; without it, "
                "remediation has nowhere to go."
            ),
            failing=failing,
        ),
        *domain_breakdown(
            "GV-001",
            "governance",
            title="Tier-1 owner coverage",
            buckets=buckets,
            unit="Tier-1 datasets",
        ),
    ]


@check("GV-002", title="Ownership verified within 12 months", pillar="governance", requires={"datasets"})
def owner_verification(estate: Estate) -> list[EvidenceRecord]:
    """Owners re-attested inside the verification window."""
    tier1 = estate.tier1
    cutoff = estate.harvested_at - timedelta(days=OWNER_VERIFICATION_WINDOW_DAYS)
    verified, failing = 0, []
    for dataset in tier1:
        verified_at = dataset.owner_verified_at
        if verified_at is not None and verified_at.replace(tzinfo=cutoff.tzinfo) >= cutoff:
            verified += 1
        else:
            failing.append(dataset.urn)
    return [
        ratio_evidence(
            "GV-002",
            "governance",
            title="Ownership verification freshness",
            numerator=verified,
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) had ownership verified within the last "
                f"{OWNER_VERIFICATION_WINDOW_DAYS} days. Stale ownership records read as governed "
                "while routing findings to people who have moved on."
            ),
            failing=failing,
        )
    ]


@check(
    "GV-003",
    title="Certification workflow throughput",
    pillar="governance",
    requires={"governance_program"},
)
def certification_throughput(estate: Estate) -> list[EvidenceRecord]:
    """Are certification workflows actually completing, or just opening?"""
    opened = sum(p.certifications_opened for p in estate.governance_programs)
    completed = sum(p.certifications_completed for p in estate.governance_programs)
    tools = ", ".join(sorted({p.tool for p in estate.governance_programs})) or "none"
    return [
        ratio_evidence(
            "GV-003",
            "governance",
            title="Certification workflow throughput",
            numerator=completed,
            denominator=opened,
            unit="certification workflows",
            rationale_template=(
                "{numerator} of {denominator} {unit} opened in the window have completed ({pct}%), "
                f"across: {tools}. A workflow backlog means the catalog records intent rather than state."
            ),
        )
    ]


@check("GV-004", title="Curation of top-queried assets", pillar="governance", requires={"datasets", "usage"})
def catalog_curation(estate: Estate) -> list[EvidenceRecord]:
    """The most-queried assets are the ones agents will hit first."""
    totals: dict[str, int] = {}
    for event in estate.usage:
        totals[event.dataset_urn] = totals.get(event.dataset_urn, 0) + event.query_count
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:TOP_QUERIED_SAMPLE]
    if not ranked:
        return []
    curated, failing = 0, []
    for urn, queries in ranked:
        dataset = estate.dataset_by_urn(urn)
        if dataset is not None and dataset.catalog_curated:
            curated += 1
        else:
            failing.append(f"{urn} ({queries} queries)")
    return [
        ratio_evidence(
            "GV-004",
            "governance",
            title="Curation of top-queried assets",
            numerator=curated,
            denominator=len(ranked),
            unit="top-queried datasets",
            rationale_template=(
                "{numerator} of the {denominator} most-queried datasets ({pct}%) are curated in the "
                "catalog. Uncurated high-traffic assets are precisely the ones a copilot will "
                "surface without context."
            ),
            failing=failing,
        )
    ]


@check(
    "GV-005",
    title="Catalog/platform classification agreement",
    pillar="governance",
    requires={"columns", "classification"},
)
def classification_agreement(estate: Estate) -> list[EvidenceRecord]:
    """A column marked PII in one system and not the other is a high-severity gap."""
    compared, agreed, failing = 0, 0, []
    for dataset, column in estate.all_columns:
        platform_class = (column.platform_classification or "").lower()
        catalog_class = (column.catalog_classification or "").lower()
        if not platform_class and not catalog_class:
            continue
        compared += 1
        if platform_class == catalog_class:
            agreed += 1
        else:
            failing.append(
                f"{dataset.urn}.{column.name} (platform={platform_class or 'none'}, "
                f"catalog={catalog_class or 'none'})"
            )
    return [
        ratio_evidence(
            "GV-005",
            "governance",
            title="Classification agreement across catalog and platform",
            numerator=agreed,
            denominator=compared,
            unit="classified columns",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) carry the same classification in the "
                "catalog and on the platform. Disagreement means protection is being applied from a "
                "different picture of sensitivity than the one governance believes it has."
            ),
            failing=failing,
            confidence=CONFIDENCE_RECONCILED,
        )
    ]


@check("GV-006", title="Glossary liveness", pillar="governance", requires={"governance_program"})
def glossary_liveness(estate: Estate) -> list[EvidenceRecord]:
    """Certified terms actually linked to physical columns."""
    terms = sum(p.glossary_terms for p in estate.governance_programs)
    linked = sum(p.glossary_terms_linked for p in estate.governance_programs)
    return [
        ratio_evidence(
            "GV-006",
            "governance",
            title="Glossary liveness",
            numerator=linked,
            denominator=terms,
            unit="glossary terms",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are linked to a physical column or "
                "semantic measure. Unlinked terms are documentation, not machine-usable meaning."
            ),
        )
    ]


@check("GV-007", title="Access review currency", pillar="governance", requires={"governance_program"})
def access_reviews(estate: Estate) -> list[EvidenceRecord]:
    """Access reviews completed inside their cycle."""
    programs = estate.governance_programs
    if not programs:
        return []
    current = [p for p in programs if p.access_reviews_current]
    failing = [p.tool for p in programs if not p.access_reviews_current]
    return [
        ratio_evidence(
            "GV-007",
            "governance",
            title="Access review currency",
            numerator=len(current),
            denominator=len(programs),
            unit="governance programmes",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have access reviews current. Lapsed "
                "reviews mean the entitlement picture an agent inherits has not been checked by anyone."
            ),
            failing=failing,
        )
    ]


@check("GV-008", title="Steward response latency", pillar="governance", requires={"governance_program"})
def steward_latency(estate: Estate) -> list[EvidenceRecord]:
    """Median steward response time, normalised against a 48-hour target."""
    latencies = [
        p.median_steward_response_hours
        for p in estate.governance_programs
        if p.median_steward_response_hours is not None
    ]
    if not latencies:
        return []
    observed = sum(latencies) / len(latencies)
    span = STEWARD_LATENCY_FLOOR_HOURS - STEWARD_LATENCY_TARGET_HOURS
    result = round(max(0.0, min(100.0, 100.0 * (STEWARD_LATENCY_FLOOR_HOURS - observed) / span)), 4)
    return [
        EvidenceRecord(
            check_id="GV-008",
            pillar_key="governance",
            result=result,
            measured={"median_response_hours": round(observed, 1), "target_hours": STEWARD_LATENCY_TARGET_HOURS},
            rationale=(
                f"Median steward response latency is {observed:.0f} hours against a "
                f"{STEWARD_LATENCY_TARGET_HOURS:.0f}-hour target. Stewardship that answers in weeks "
                "cannot support a review queue for AI-generated findings."
            ),
            severity=severity_for(result),
            confidence=CONFIDENCE_DECLARED,
        )
    ]


@check("GV-009", title="Questionnaire contradiction check", pillar="governance", requires={"datasets"})
def questionnaire_contradictions(estate: Estate) -> list[EvidenceRecord]:
    """Self-reported claims that machine evidence contradicts are themselves findings."""
    claims = {
        "Q-GOV-04": ("lineage coverage", _measured_lineage_coverage(estate)),
        "Q-GOV-02": ("Tier-1 owner coverage", _measured_owner_coverage(estate)),
    }
    contradictions = []
    checked = 0
    for question_id, (label, measured) in claims.items():
        response = estate.questionnaire_answer(question_id)
        if response is None or response.numeric_answer is None or measured is None:
            continue
        checked += 1
        gap = response.numeric_answer - measured
        if gap > 20:
            contradictions.append(
                f"{question_id}: claimed {response.numeric_answer:.0f}% {label}, measured {measured:.0f}%"
            )
    if not checked:
        return []
    result = pct(checked - len(contradictions), checked)
    return [
        EvidenceRecord(
            check_id="GV-009",
            pillar_key="governance",
            result=result,
            measured={"claims_checked": checked, "contradictions": len(contradictions)},
            rationale=(
                f"{len(contradictions)} of {checked} self-reported claims are contradicted by machine "
                "evidence by more than 20 points. A confident but wrong picture of the estate is a "
                "governance finding in its own right."
            ),
            severity=severity_for(result),
            failing_targets=contradictions,
            confidence=CONFIDENCE_DERIVED,
        )
    ]


def _measured_lineage_coverage(estate: Estate) -> float | None:
    tier1 = estate.tier1
    if not tier1:
        return None
    with_lineage = sum(1 for d in tier1 if estate.upstream_of(d.urn))
    return pct(with_lineage, len(tier1))


def _measured_owner_coverage(estate: Estate) -> float | None:
    tier1 = estate.tier1
    if not tier1:
        return None
    return pct(sum(1 for d in tier1 if d.owner), len(tier1))
