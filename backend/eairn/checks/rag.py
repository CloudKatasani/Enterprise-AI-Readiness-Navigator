"""RAG Readiness checks (RG-xxx): coverage, chunkability, vectors, ACLs, evaluation."""

from __future__ import annotations

from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    CONFIDENCE_DERIVED,
    Estate,
    EvidenceRecord,
    check,
    pct,
    ratio_evidence,
    severity_for,
)


@check("RG-001", title="Authoritative content indexed", pillar="rag_readiness", requires={"rag_corpora"})
def content_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Coverage of authoritative sources, penalised for stale and duplicate content."""
    corpora = estate.rag_corpora
    if not corpora:
        return []
    authoritative = sum(c.authoritative_doc_count for c in corpora)
    indexed = sum(min(c.indexed_doc_count, c.authoritative_doc_count) for c in corpora)
    stale = sum(c.stale_doc_count for c in corpora)
    duplicates = sum(c.duplicate_doc_count for c in corpora)
    total_indexed = sum(c.indexed_doc_count for c in corpora) or 1
    coverage = pct(indexed, authoritative)
    contamination = (stale + duplicates) / total_indexed
    result = round(max(0.0, coverage * (1.0 - min(contamination, 0.5))), 4)
    failing = [
        f"{c.name} ({c.indexed_doc_count}/{c.authoritative_doc_count} indexed, "
        f"{c.stale_doc_count} stale, {c.duplicate_doc_count} duplicate)"
        for c in corpora
        if c.indexed_doc_count < c.authoritative_doc_count or c.stale_doc_count or c.duplicate_doc_count
    ]
    return [
        EvidenceRecord(
            check_id="RG-001",
            pillar_key="rag_readiness",
            result=result,
            measured={
                "authoritative_docs": authoritative,
                "indexed_docs": indexed,
                "stale_docs": stale,
                "duplicate_docs": duplicates,
                "raw_coverage_pct": coverage,
            },
            rationale=(
                f"{indexed} of {authoritative} authoritative documents are indexed ({coverage:.1f}% "
                f"coverage), with {stale} stale and {duplicates} duplicate documents in the index "
                f"({contamination:.0%} contamination). Coverage is discounted by contamination because "
                "an index that retrieves superseded content is worse than one that retrieves nothing."
            ),
            severity=severity_for(result),
            failing_targets=failing,
            confidence=CONFIDENCE_DECLARED,
        )
    ]


@check("RG-002", title="Chunk-level filterable metadata", pillar="rag_readiness", requires={"rag_corpora"})
def chunk_metadata(estate: Estate) -> list[EvidenceRecord]:
    """Owner, date, classification and audience -- the four attributes retrieval filters on."""
    corpora = estate.rag_corpora
    if not corpora:
        return []
    total = sum(c.indexed_doc_count for c in corpora)
    if total == 0:
        return []
    complete = sum(
        min(c.docs_with_owner, c.docs_with_date, c.docs_with_classification, c.docs_with_audience)
        for c in corpora
    )
    failing = []
    for corpus in corpora:
        gaps = []
        for label, value in (
            ("owner", corpus.docs_with_owner),
            ("date", corpus.docs_with_date),
            ("classification", corpus.docs_with_classification),
            ("audience", corpus.docs_with_audience),
        ):
            if corpus.indexed_doc_count and value < corpus.indexed_doc_count:
                gaps.append(f"{label} on {corpus.indexed_doc_count - value} docs")
        if gaps:
            failing.append(f"{corpus.name} (missing {', '.join(gaps)})")
    return [
        ratio_evidence(
            "RG-002",
            "rag_readiness",
            title="Chunk-level filterable metadata",
            numerator=complete,
            denominator=total,
            unit="indexed documents",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) carry all four filterable attributes "
                "(owner, date, classification, audience). Missing attributes mean retrieval cannot be "
                "scoped by recency, sensitivity or audience -- the three filters that keep answers safe."
            ),
            failing=failing,
        )
    ]


@check("RG-003", title="Format census / chunkability", pillar="rag_readiness", requires={"rag_corpora"})
def chunking_readiness(estate: Estate) -> list[EvidenceRecord]:
    """Scanned and table-heavy documents need specialised handling before they chunk cleanly."""
    corpora = estate.rag_corpora
    total = sum(c.indexed_doc_count for c in corpora)
    if total == 0:
        return []
    structured = sum(c.structured_doc_count for c in corpora)
    scanned = sum(c.scanned_doc_count for c in corpora)
    table_heavy = sum(c.table_heavy_doc_count for c in corpora)
    # Table-heavy documents are workable with specialised handling; scanned ones
    # are not chunkable at all without OCR, so they are weighted more harshly.
    penalty = (scanned + 0.5 * table_heavy) / total
    result = round(max(0.0, min(100.0, pct(structured, total) * (1 - min(penalty, 0.6)))), 4)
    return [
        EvidenceRecord(
            check_id="RG-003",
            pillar_key="rag_readiness",
            result=result,
            measured={
                "indexed_docs": total,
                "structured_docs": structured,
                "scanned_docs": scanned,
                "table_heavy_docs": table_heavy,
            },
            rationale=(
                f"{structured} of {total} indexed documents ({pct(structured, total):.1f}%) have "
                f"structure amenable to chunking; {scanned} are scanned images needing OCR and "
                f"{table_heavy} are table-heavy and need specialised extraction. The score discounts "
                "structured coverage by that handling burden."
            ),
            severity=severity_for(result),
            failing_targets=[
                f"{c.name} ({c.scanned_doc_count} scanned, {c.table_heavy_doc_count} table-heavy)"
                for c in corpora
                if c.scanned_doc_count or c.table_heavy_doc_count
            ],
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check("RG-004", title="Embedding refresh vs. content change rate", pillar="rag_readiness", requires={"rag_corpora"})
def vector_discipline(estate: Estate) -> list[EvidenceRecord]:
    """A refresh cadence slower than the content changes guarantees stale retrieval."""
    corpora = estate.rag_corpora
    if not corpora:
        return []
    scored, failing = [], []
    for corpus in corpora:
        if not corpus.vector_store:
            scored.append(0.0)
            failing.append(f"{corpus.name} (no vector store)")
            continue
        if corpus.embedding_refresh_hours is None or corpus.content_change_hours is None:
            scored.append(50.0)
            failing.append(f"{corpus.name} (refresh SLA not declared)")
            continue
        ratio = corpus.embedding_refresh_hours / max(corpus.content_change_hours, 1e-6)
        # refresh at least as often as content changes -> 100; 4x slower -> 0.
        corpus_score = max(0.0, min(100.0, 100.0 * (4.0 - ratio) / 3.0))
        scored.append(corpus_score)
        if corpus_score < 90:
            failing.append(
                f"{corpus.name} (refresh every {corpus.embedding_refresh_hours:.0f}h vs content "
                f"changing every {corpus.content_change_hours:.0f}h)"
            )
    result = round(sum(scored) / len(scored), 4)
    return [
        EvidenceRecord(
            check_id="RG-004",
            pillar_key="rag_readiness",
            result=result,
            measured={"corpora": len(corpora), "per_corpus_scores": [round(s, 2) for s in scored]},
            rationale=(
                f"Mean vector-refresh discipline across {len(corpora)} corpora is {result:.1f}%. Full "
                "marks require embeddings to refresh at least as often as the underlying content "
                "changes; a corpus refreshing four times slower than it changes scores zero."
            ),
            severity=severity_for(result),
            failing_targets=failing,
            confidence=CONFIDENCE_DECLARED,
        )
    ]


@check("RG-005", title="Permission-aware retrieval", pillar="rag_readiness", requires={"rag_corpora"})
def acl_propagation(estate: Estate) -> list[EvidenceRecord]:
    """Hard blocker: classified content indexed without retrieval-time filter enforcement."""
    corpora = estate.rag_corpora
    if not corpora:
        return []
    safe, failing = 0, []
    for corpus in corpora:
        if corpus.acl_propagated and corpus.retrieval_filter_enforced:
            safe += 1
            continue
        reasons = []
        if not corpus.acl_propagated:
            reasons.append("source ACLs do not propagate to the index")
        if not corpus.retrieval_filter_enforced:
            reasons.append("no filter enforcement at retrieval time")
        if corpus.contains_classified:
            reasons.append("index contains classified content")
        failing.append(f"{corpus.name} ({'; '.join(reasons)})")
    record = ratio_evidence(
        "RG-005",
        "rag_readiness",
        title="Permission-aware retrieval",
        numerator=safe,
        denominator=len(corpora),
        unit="corpora",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) propagate source ACLs into the index and "
            "enforce them at retrieval time. Classified content in an index without filter "
            "enforcement is a direct disclosure channel and triggers the RRI hard-blocker cap."
        ),
        failing=failing,
    )
    if failing:
        record.severity = "critical"
    return [record]


@check("RG-006", title="Groundedness measurement in place", pillar="rag_readiness", requires={"rag_corpora"})
def groundedness_eval(estate: Estate) -> list[EvidenceRecord]:
    """Retrieval eval sets, citation enforcement, hallucination monitoring."""
    corpora = estate.rag_corpora
    if not corpora:
        return []
    signals, possible, failing = 0, 0, []
    for corpus in corpora:
        present = [corpus.eval_set_present, corpus.citation_enforced, corpus.hallucination_monitoring]
        signals += sum(1 for value in present if value)
        possible += len(present)
        missing = [
            label
            for label, value in zip(
                ("retrieval eval set", "citation enforcement", "hallucination monitoring"), present
            )
            if not value
        ]
        if missing:
            failing.append(f"{corpus.name} (missing {', '.join(missing)})")
    return [
        ratio_evidence(
            "RG-006",
            "rag_readiness",
            title="Groundedness measurement in place",
            numerator=signals,
            denominator=possible,
            unit="groundedness controls",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are in place across the corpora "
                "(retrieval eval set, citation enforcement, hallucination monitoring). Without them a "
                "RAG regression is only discovered by the person who trusted the answer."
            ),
            failing=failing,
        )
    ]
