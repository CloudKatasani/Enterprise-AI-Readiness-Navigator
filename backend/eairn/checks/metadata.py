"""Metadata checks (MD-xxx): can humans *and machines* discover and understand data?"""

from __future__ import annotations

from datetime import timedelta

from eairn.checks.base import (
    CONFIDENCE_DERIVED,
    CONFIDENCE_INFERRED,
    Estate,
    EvidenceRecord,
    check,
    domain_breakdown,
    ratio_evidence,
)

STALE_DAYS = 90
MIN_DESCRIPTION_CHARS = 12


def _is_described(text: str | None) -> bool:
    """A placeholder description is worse than none -- it looks like coverage."""
    if not text:
        return False
    cleaned = text.strip()
    if len(cleaned) < MIN_DESCRIPTION_CHARS:
        return False
    return cleaned.lower() not in {"tbd", "todo", "n/a", "no description", "placeholder"}


@check("MD-001", title="Column description coverage", pillar="metadata", requires={"columns", "descriptions"})
def column_description_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Column-level descriptions, weighted so Tier-1 gaps cannot be masked by sandbox coverage."""
    records: list[EvidenceRecord] = []
    for tier_label, datasets in (("Tier-1", estate.tier1), ("all", estate.datasets)):
        described = total = 0
        failing: list[str] = []
        for dataset in datasets:
            for column in dataset.columns:
                total += 1
                if _is_described(column.description):
                    described += 1
                elif tier_label == "Tier-1":
                    failing.append(f"{dataset.urn}.{column.name}")
        if total == 0:
            continue
        record = ratio_evidence(
            "MD-001",
            "metadata",
            title=f"Column description coverage ({tier_label})",
            numerator=described,
            denominator=total,
            unit=f"{tier_label} columns",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) carry a meaningful description "
                "(placeholders such as 'TBD' are not counted). Column semantics are what let an "
                "agent choose the right field instead of a plausible one."
            ),
            failing=failing,
            target_type="tier" if tier_label == "Tier-1" else "estate",
            target_urn=f"scope:{tier_label}",
        )
        records.append(record)
    # Tier-1 coverage is the scored record; the estate-wide record is context.
    if len(records) == 2:
        records[1].check_id = "MD-001.context"

    buckets: dict[str, tuple[float, float, str]] = {}
    for dataset in estate.datasets:
        domain = dataset.domain or "unassigned"
        described, total, _ = buckets.get(domain, (0.0, 0.0, dataset.platform))
        described += sum(1 for c in dataset.columns if _is_described(c.description))
        total += len(dataset.columns)
        buckets[domain] = (described, total, dataset.platform)
    records.extend(
        domain_breakdown(
            "MD-001", "metadata", title="Column description coverage", buckets=buckets, unit="columns"
        )
    )
    return records


@check("MD-002", title="Table description coverage", pillar="metadata", requires={"datasets", "descriptions"})
def table_description_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Dataset-level descriptions across the estate."""
    described = [d for d in estate.datasets if _is_described(d.description)]
    failing = [d.urn for d in estate.datasets if not _is_described(d.description) and d.tier <= 2]
    return [
        ratio_evidence(
            "MD-002",
            "metadata",
            title="Table description coverage",
            numerator=len(described),
            denominator=len(estate.datasets),
            unit="datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have a meaningful description. Tier-1 "
                "and Tier-2 gaps are listed as failing targets."
            ),
            failing=failing,
        )
    ]


@check("MD-003", title="Business glossary linkage", pillar="metadata", requires={"columns"})
def glossary_linkage(estate: Estate) -> list[EvidenceRecord]:
    """Tier-1 columns linked to a governed business term."""
    linked = total = 0
    failing: list[str] = []
    for dataset in estate.tier1:
        for column in dataset.columns:
            total += 1
            if column.glossary_term:
                linked += 1
            else:
                failing.append(f"{dataset.urn}.{column.name}")
    return [
        ratio_evidence(
            "MD-003",
            "metadata",
            title="Business glossary linkage (Tier-1 columns)",
            numerator=linked,
            denominator=total,
            unit="Tier-1 columns",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are linked to a business glossary term. "
                "Glossary linkage is what makes a natural-language question resolvable to one column."
            ),
            failing=failing,
        )
    ]


@check("MD-004", title="Tier-1 lineage completeness", pillar="metadata", requires={"datasets", "lineage"})
def tier1_lineage(estate: Estate) -> list[EvidenceRecord]:
    """Tier-1 datasets with resolvable upstream lineage."""
    tier1 = estate.tier1
    resolvable, failing = 0, []
    for dataset in tier1:
        if estate.upstream_of(dataset.urn):
            resolvable += 1
        else:
            failing.append(dataset.urn)
    return [
        ratio_evidence(
            "MD-004",
            "metadata",
            title="Tier-1 lineage completeness",
            numerator=resolvable,
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have resolvable upstream lineage. "
                "Without it, neither an impact analysis nor an agent citation can be produced."
            ),
            failing=failing,
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check(
    "MD-005",
    title="Column-level lineage resolvability",
    pillar="metadata",
    requires={"lineage"},
)
def column_lineage(estate: Estate) -> list[EvidenceRecord]:
    """Column-level edges are frequently inferred from query history, so confidence is marked down."""
    column_edges = [e for e in estate.lineage if e.level == "column"]
    tier1 = estate.tier1
    if not tier1:
        return []
    resolved, failing = 0, []
    edges_by_downstream = {}
    for edge in column_edges:
        edges_by_downstream.setdefault(edge.downstream_urn, []).append(edge)
    for dataset in tier1:
        edges = edges_by_downstream.get(dataset.urn, [])
        covered_columns = {e.downstream_column for e in edges if e.downstream_column}
        if dataset.columns and len(covered_columns) >= 0.8 * len(dataset.columns):
            resolved += 1
        else:
            failing.append(f"{dataset.urn} ({len(covered_columns)}/{len(dataset.columns)} columns)")
    inferred_edges = [e for e in column_edges if e.source in {"access_history", "query_log", "inferred"}]
    confidence = CONFIDENCE_INFERRED if len(inferred_edges) > len(column_edges) / 2 else CONFIDENCE_DERIVED
    return [
        ratio_evidence(
            "MD-005",
            "metadata",
            title="Column-level lineage resolvability",
            numerator=resolved,
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) resolve column-level lineage for at "
                "least 80% of their columns. Column lineage is the substrate for agent citations "
                "and for mechanical classification propagation."
            ),
            failing=failing,
            confidence=confidence,
            extra={
                "column_edges": len(column_edges),
                "inferred_edges": len(inferred_edges),
                "confidence_reason": (
                    "majority of column edges are inferred from query history rather than declared"
                    if confidence == CONFIDENCE_INFERRED
                    else "edges are platform-declared or graph-derived"
                ),
            },
        )
    ]


@check("MD-006", title="Stale / orphaned asset hygiene", pillar="metadata", requires={"datasets", "usage"})
def stale_assets(estate: Estate) -> list[EvidenceRecord]:
    """Unqueried assets still carrying storage cost -- and RAG-index exclusion candidates."""
    cutoff = estate.harvested_at - timedelta(days=STALE_DAYS)
    active, stale_urns, stale_bytes = 0, [], 0
    for dataset in estate.datasets:
        last = dataset.last_queried_at
        if last is not None and last.replace(tzinfo=cutoff.tzinfo) >= cutoff:
            active += 1
        else:
            stale_urns.append(dataset.urn)
            stale_bytes += dataset.bytes or 0
    return [
        ratio_evidence(
            "MD-006",
            "metadata",
            title="Stale / orphaned asset hygiene",
            numerator=active,
            denominator=len(estate.datasets),
            unit="datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) were queried in the last "
                f"{STALE_DAYS} days. Stale assets carry storage cost and are prime candidates for "
                "exclusion from RAG indexes and agent tool surfaces."
            ),
            failing=stale_urns,
            extra={"stale_bytes": stale_bytes, "window_days": STALE_DAYS},
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check("MD-007", title="Assets under a governed catalog", pillar="metadata", requires={"datasets"})
def governed_catalog(estate: Estate) -> list[EvidenceRecord]:
    """Legacy, ungoverned metastores holding Tier-1 data are a high-severity finding."""
    governed = [d for d in estate.datasets if d.governed]
    failing = [d.urn for d in estate.datasets if not d.governed]
    tier1_ungoverned = [d.urn for d in estate.tier1 if not d.governed]
    record = ratio_evidence(
        "MD-007",
        "metadata",
        title="Assets under a governed catalog",
        numerator=len(governed),
        denominator=len(estate.datasets),
        unit="datasets",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) sit under a governed catalog. Assets "
            "outside it inherit no policy, no tags and no lineage."
        ),
        failing=failing,
        extra={"tier1_ungoverned": tier1_ungoverned},
    )
    if tier1_ungoverned:
        record.severity = "high"
        record.rationale += (
            f" {len(tier1_ungoverned)} of the ungoverned assets are Tier-1, which is a "
            "high-severity finding on its own."
        )
    return [record]
