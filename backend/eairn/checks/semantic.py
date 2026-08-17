"""Semantic layer checks (SL-xxx): is business logic defined once and queryable?"""

from __future__ import annotations

from collections import defaultdict

from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    CONFIDENCE_SELF_REPORTED,
    Estate,
    EvidenceRecord,
    check,
    pct,
    ratio_evidence,
    severity_for,
)


@check("SL-001", title="Exactly one definition per certified KPI", pillar="semantic_layer", requires={"kpi_definitions"})
def kpi_single_definition(estate: Estate) -> list[EvidenceRecord]:
    """Same KPI name, divergent expressions -- the direct blocker for NL-query trust."""
    by_name: dict[str, set[str]] = defaultdict(set)
    models: dict[str, set[str]] = defaultdict(set)
    for definition in estate.kpi_definitions:
        by_name[definition.kpi_name].add(definition.expression_hash)
        models[definition.kpi_name].add(definition.semantic_model)
    if not by_name:
        return []
    single = [name for name, hashes in by_name.items() if len(hashes) == 1]
    duplicated = sorted(name for name, hashes in by_name.items() if len(hashes) > 1)
    failing = [
        f"{name}: {len(by_name[name])} divergent definitions across {', '.join(sorted(models[name]))}"
        for name in duplicated
    ]
    return [
        ratio_evidence(
            "SL-001",
            "semantic_layer",
            title="Exactly one definition per KPI",
            numerator=len(single),
            denominator=len(by_name),
            unit="KPIs",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have exactly one physical definition. "
                "A KPI with two definitions gives two different answers to the same natural-language "
                "question, which is indistinguishable from a hallucination to the person asking."
            ),
            failing=failing,
        )
    ]


@check("SL-002", title="Certified semantic model coverage", pillar="semantic_layer", requires={"semantic_models"})
def certified_model_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Weighted by report traffic: certification of the models people actually use."""
    models = estate.semantic_models
    if not models:
        return []
    total_views = sum(m.report_views for m in models)
    if total_views == 0:
        numerator = sum(1 for m in models if m.certified)
        denominator = len(models)
        unit = "semantic models"
    else:
        numerator = sum(m.report_views for m in models if m.certified)
        denominator = total_views
        unit = "report views"
    failing = [f"{m.name} ({m.report_views} views)" for m in models if not m.certified]
    return [
        ratio_evidence(
            "SL-002",
            "semantic_layer",
            title="Certified semantic model coverage",
            numerator=numerator,
            denominator=denominator,
            unit=unit,
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are served by a certified semantic model. "
                "Uncertified models carrying real traffic are the ones a copilot will answer from."
            ),
            failing=failing,
        )
    ]


@check("SL-003", title="Semantic field description coverage", pillar="semantic_layer", requires={"semantic_models"})
def field_descriptions(estate: Estate) -> list[EvidenceRecord]:
    """Fields without descriptions cannot be selected reliably by an NL layer."""
    models = estate.semantic_models
    fields = sum(m.field_count for m in models)
    described = sum(m.described_field_count for m in models)
    failing = [
        f"{m.name} ({m.field_count - m.described_field_count} undescribed of {m.field_count})"
        for m in models
        if m.field_count and m.described_field_count < 0.7 * m.field_count
    ]
    if fields == 0:
        return []
    return [
        ratio_evidence(
            "SL-003",
            "semantic_layer",
            title="Semantic field description coverage",
            numerator=described,
            denominator=fields,
            unit="semantic fields",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are described. Models missing "
                "descriptions on more than 30% of fields are listed for per-model remediation."
            ),
            failing=failing,
        )
    ]


@check("SL-004", title="Semantic field synonym coverage", pillar="semantic_layer", requires={"semantic_models"})
def field_synonyms(estate: Estate) -> list[EvidenceRecord]:
    """Synonyms are how a business question reaches the right field."""
    models = estate.semantic_models
    fields = sum(m.field_count for m in models)
    with_synonyms = sum(m.synonym_field_count for m in models)
    if fields == 0:
        return []
    return [
        ratio_evidence(
            "SL-004",
            "semantic_layer",
            title="Semantic field synonym coverage",
            numerator=with_synonyms,
            denominator=fields,
            unit="semantic fields",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) carry synonyms. Without them, a question "
                "phrased in business language misses fields named in warehouse language."
            ),
            failing=[m.name for m in models if m.field_count and m.synonym_field_count < 0.5 * m.field_count],
        )
    ]


@check("SL-005", title="NL answer acceptance rate", pillar="semantic_layer", requires={"semantic_models"})
def nl_acceptance(estate: Estate) -> list[EvidenceRecord]:
    """Measured acceptance where instrumented; questionnaire fallback is marked low-confidence."""
    measured = [m.nl_answer_acceptance for m in estate.semantic_models if m.nl_answer_acceptance is not None]
    if measured:
        result = round(100.0 * sum(measured) / len(measured), 4)
        return [
            EvidenceRecord(
                check_id="SL-005",
                pillar_key="semantic_layer",
                result=result,
                measured={"instrumented_models": len(measured), "mean_acceptance": round(result / 100, 4)},
                rationale=(
                    f"Mean natural-language answer acceptance across {len(measured)} instrumented semantic "
                    f"models is {result:.1f}%. This is the closest available proxy for whether the "
                    "semantic layer can actually carry a copilot."
                ),
                severity=severity_for(result),
                confidence=CONFIDENCE_DECLARED,
            )
        ]
    response = estate.questionnaire_answer("Q-QS-04")
    if response is None or response.numeric_answer is None:
        return []
    result = float(max(0.0, min(100.0, response.numeric_answer)))
    return [
        EvidenceRecord(
            check_id="SL-005",
            pillar_key="semantic_layer",
            result=result,
            measured={"source": "questionnaire", "question_id": "Q-QS-04"},
            rationale=(
                f"No NL instrumentation was found; the reported answer-acceptance rate of {result:.0f}% "
                "comes from the questionnaire and is recorded at self-reported confidence, so it sits "
                "in the review queue rather than driving the score unchallenged."
            ),
            severity=severity_for(result),
            confidence=CONFIDENCE_SELF_REPORTED,
        )
    ]
