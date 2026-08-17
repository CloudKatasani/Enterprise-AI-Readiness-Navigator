"""AI Engineering checks (AE-xxx): reproducible build, track, deploy."""

from __future__ import annotations

from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    Estate,
    EvidenceRecord,
    check,
    pct,
    ratio_evidence,
    severity_for,
)


def _of_kind(estate: Estate, kind: str):
    return [a for a in estate.ml_assets if a.kind == kind]


@check("AE-001", title="Experiment tracking in use", pillar="ai_engineering", requires={"ml_assets"})
def experiment_tracking(estate: Estate) -> list[EvidenceRecord]:
    """Models with a tracked experiment behind them."""
    models = _of_kind(estate, "model")
    experiments = _of_kind(estate, "experiment")
    if not models:
        return []
    tracked_names = {e.attributes.get("model") for e in experiments if e.attributes}
    tracked = [m for m in models if m.name in tracked_names or m.attributes.get("experiment")]
    failing = [m.name for m in models if m not in tracked]
    return [
        ratio_evidence(
            "AE-001",
            "ai_engineering",
            title="Experiment tracking in use",
            numerator=len(tracked),
            denominator=len(models),
            unit="models",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) trace back to a tracked experiment. "
                "Untracked models cannot be reproduced, compared or defended in review."
            ),
            failing=failing,
        )
    ]


@check("AE-002", title="Production endpoints backed by registered models", pillar="ai_engineering", requires={"ml_assets"})
def registered_models(estate: Estate) -> list[EvidenceRecord]:
    """An unregistered production endpoint is an untraceable model in the critical path."""
    endpoints = _of_kind(estate, "endpoint")
    if not endpoints:
        return []
    registered = [e for e in endpoints if e.registered]
    failing = [e.name for e in endpoints if not e.registered]
    record = ratio_evidence(
        "AE-002",
        "ai_engineering",
        title="Production endpoints backed by registered models",
        numerator=len(registered),
        denominator=len(endpoints),
        unit="production endpoints",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) are backed by a registered model version. "
            "Unregistered endpoints have no version, no owner and no rollback path."
        ),
        failing=failing,
    )
    if failing:
        record.severity = "high" if record.result >= 50 else "critical"
    return [record]


@check("AE-003", title="Model-to-training-data lineage", pillar="ai_engineering", requires={"ml_assets"})
def training_lineage(estate: Estate) -> list[EvidenceRecord]:
    """Can you say which data produced a given prediction?"""
    models = _of_kind(estate, "model") + _of_kind(estate, "endpoint")
    if not models:
        return []
    with_lineage = [m for m in models if m.training_data_lineage]
    return [
        ratio_evidence(
            "AE-003",
            "ai_engineering",
            title="Model-to-training-data lineage",
            numerator=len(with_lineage),
            denominator=len(models),
            unit="models and endpoints",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) have resolvable lineage to their training "
                "data. Without it, a data incident cannot be mapped to the models it contaminated."
            ),
            failing=[m.name for m in models if not m.training_data_lineage],
        )
    ]


@check("AE-004", title="Feature store reuse", pillar="ai_engineering", requires={"ml_assets"})
def feature_reuse(estate: Estate) -> list[EvidenceRecord]:
    """Features consumed by more than one model -- the signal that a feature store is real."""
    features = _of_kind(estate, "feature_table")
    if not features:
        return []
    reused = [f for f in features if f.consumers > 1]
    result = pct(len(reused), len(features))
    return [
        EvidenceRecord(
            check_id="AE-004",
            pillar_key="ai_engineering",
            result=result,
            measured={"feature_tables": len(features), "reused": len(reused)},
            rationale=(
                f"{len(reused)} of {len(features)} feature tables ({result:.1f}%) are consumed by more "
                "than one model. Single-consumer features are pipeline outputs with a feature-store "
                "label, and do not deliver consistency between training and serving."
            ),
            severity=severity_for(result),
            failing_targets=[f.name for f in features if f.consumers <= 1][:200],
        )
    ]


@check("AE-005", title="Human-gated model promotion", pillar="ai_engineering", requires={"ml_assets"})
def promotion_gates(estate: Estate) -> list[EvidenceRecord]:
    """Promotion to production requires an evaluation and a human decision."""
    promotable = _of_kind(estate, "model") + _of_kind(estate, "endpoint")
    if not promotable:
        return []
    gated = [m for m in promotable if m.promotion_gated]
    record = ratio_evidence(
        "AE-005",
        "ai_engineering",
        title="Human-gated model promotion",
        numerator=len(gated),
        denominator=len(promotable),
        unit="promotable assets",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) are promoted through an evaluation gate with "
            "a recorded human decision. Ungated promotion is how an unevaluated model reaches "
            "customers."
        ),
        failing=[m.name for m in promotable if not m.promotion_gated],
    )
    return [record]


@check("AE-006", title="Gateway-governed external model endpoints", pillar="ai_engineering", requires={"ml_assets"})
def gateway_governance(estate: Estate) -> list[EvidenceRecord]:
    """External LLM calls need rate limits, payload-logging policy and PII filtering."""
    external = [
        a for a in estate.ml_assets if a.kind == "endpoint" and a.attributes.get("external", False)
    ]
    if not external:
        return []
    governed = [e for e in external if e.gateway_governed]
    record = ratio_evidence(
        "AE-006",
        "ai_engineering",
        title="Gateway-governed external model endpoints",
        numerator=len(governed),
        denominator=len(external),
        unit="external model endpoints",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) sit behind an AI gateway enforcing usage "
            "tracking, payload-logging policy and PII detection. Ungoverned external calls are an "
            "unmonitored egress path for enterprise data."
        ),
        failing=[e.name for e in external if not e.gateway_governed],
        confidence=CONFIDENCE_DECLARED,
    )
    if record.failing_targets:
        record.severity = "high"
    return [record]
