"""Security checks (SE-xxx): classification, protection, least privilege, audit."""

from __future__ import annotations

from eairn.checks.base import (
    CONFIDENCE_DECLARED,
    CONFIDENCE_DERIVED,
    CONFIDENCE_INFERRED,
    Estate,
    EvidenceRecord,
    check,
    domain_breakdown,
    pct,
    ratio_evidence,
    severity_for,
)

# Name-shaped hints used only to estimate *unclassified* sensitive columns. An
# inference like this can never protect data on its own, so evidence derived
# from it is emitted at inferred confidence and lands in the review queue.
SENSITIVE_NAME_HINTS = (
    "ssn", "social_security", "email", "phone", "dob", "birth", "passport",
    "national_id", "tax_id", "iban", "account_number", "card_number", "salary",
    "compensation", "address", "postcode", "zip", "patient", "diagnosis",
)
AUDIT_RETENTION_TARGET_DAYS = 365


@check("SE-001", title="Sensitive-column classification coverage", pillar="security", requires={"columns"})
def classification_coverage(estate: Estate) -> list[EvidenceRecord]:
    """Columns that look sensitive but carry no classification on either side."""
    suspected, classified, failing = 0, 0, []
    for dataset, column in estate.all_columns:
        name = column.name.lower()
        looks_sensitive = any(hint in name for hint in SENSITIVE_NAME_HINTS)
        if not (looks_sensitive or column.is_sensitive):
            continue
        suspected += 1
        if column.is_sensitive:
            classified += 1
        else:
            failing.append(f"{dataset.urn}.{column.name}")
    if suspected == 0:
        return []
    return [
        ratio_evidence(
            "SE-001",
            "security",
            title="Sensitive-column classification coverage",
            numerator=classified,
            denominator=suspected,
            unit="candidate sensitive columns",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) are classified. Candidates are columns "
                "already classified plus columns whose names match a sensitive-data pattern; the "
                "name-pattern component is a heuristic, so this record is emitted at reduced "
                "confidence for steward confirmation."
            ),
            failing=failing,
            confidence=CONFIDENCE_INFERRED,
        )
    ]


@check(
    "SE-002",
    title="Protection on classified columns",
    pillar="security",
    requires={"columns", "classification", "policies"},
)
def classified_protection(estate: Estate) -> list[EvidenceRecord]:
    """Hard blocker: a classified column with no masking, redaction or policy tag."""
    classified, protected, failing = 0, 0, []
    buckets: dict[str, tuple[float, float, str]] = {}
    for dataset, column in estate.all_columns:
        if not column.is_sensitive:
            continue
        classified += 1
        domain = dataset.domain or "unassigned"
        num, den, _ = buckets.get(domain, (0.0, 0.0, dataset.platform))
        buckets[domain] = (num + (1 if column.protected else 0), den + 1, dataset.platform)
        if column.protected:
            protected += 1
        else:
            failing.append(f"{dataset.urn}.{column.name}")
    if classified == 0:
        return []
    record = ratio_evidence(
        "SE-002",
        "security",
        title="Protection on classified columns",
        numerator=protected,
        denominator=classified,
        unit="classified columns",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) are covered by a masking policy, "
            "redaction rule or policy tag. Every unprotected classified column is an unmitigated "
            "disclosure path and triggers the Security hard-blocker cap."
        ),
        failing=failing,
        confidence=CONFIDENCE_DECLARED,
    )
    if failing:
        record.severity = "critical"
    return [
        record,
        *domain_breakdown(
            "SE-002",
            "security",
            title="Protection on classified columns",
            buckets=buckets,
            unit="classified columns",
        ),
    ]


@check(
    "SE-003",
    title="Classification propagation across lineage",
    pillar="security",
    requires={"columns", "classification", "lineage"},
)
def tag_propagation(estate: Estate) -> list[EvidenceRecord]:
    """Sensitivity must propagate mechanically to every lineage descendant."""
    sensitive_sources = {
        (dataset.urn, column.name)
        for dataset, column in estate.all_columns
        if column.is_sensitive
    }
    if not sensitive_sources:
        return []
    column_edges = [e for e in estate.lineage if e.level == "column"]
    checked, propagated, failing = 0, 0, []
    for edge in column_edges:
        if (edge.upstream_urn, edge.upstream_column) not in sensitive_sources:
            continue
        downstream = estate.dataset_by_urn(edge.downstream_urn)
        if downstream is None:
            continue
        target = next((c for c in downstream.columns if c.name == edge.downstream_column), None)
        if target is None:
            continue
        checked += 1
        if target.is_sensitive:
            propagated += 1
        else:
            failing.append(
                f"{edge.downstream_urn}.{edge.downstream_column} "
                f"(inherits from {edge.upstream_urn}.{edge.upstream_column})"
            )
    if checked == 0:
        return []
    return [
        ratio_evidence(
            "SE-003",
            "security",
            title="Classification propagation across lineage",
            numerator=propagated,
            denominator=checked,
            unit="downstream columns of classified sources",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) inherit the upstream classification. "
                "Propagation that depends on someone remembering is how sensitive data reaches an "
                "unprotected mart."
            ),
            failing=failing,
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check("SE-004", title="Direct-to-user grant hygiene", pillar="security", requires={"grants"})
def direct_grants(estate: Estate) -> list[EvidenceRecord]:
    """Grants bypassing functional roles are unreviewable and un-revocable at scale."""
    grants = estate.grants
    if not grants:
        return []
    direct = [g for g in grants if g.grantee_type == "user" and g.object_urn]
    result = pct(len(grants) - len(direct), len(grants))
    return [
        EvidenceRecord(
            check_id="SE-004",
            pillar_key="security",
            result=result,
            measured={"grants": len(grants), "direct_to_user": len(direct)},
            rationale=(
                f"{len(direct)} of {len(grants)} grants ({100 - result:.1f}%) are made directly to a "
                "human identity on an object rather than through a functional role. Direct grants "
                "bypass access review and do not survive a joiner/mover/leaver process."
            ),
            severity=severity_for(result),
            failing_targets=[f"{g.grantee} -> {g.privilege} on {g.object_urn}" for g in direct][:200],
        )
    ]


@check("SE-005", title="Admin role fan-out", pillar="security", requires={"grants"})
def admin_fanout(estate: Estate) -> list[EvidenceRecord]:
    """How many identities hold account-admin-class privilege."""
    admin_grants = [g for g in estate.grants if g.is_admin_role]
    holders = sorted({g.grantee for g in admin_grants})
    total_identities = len({g.grantee for g in estate.grants}) or 1
    share = len(holders) / total_identities
    # 100 at <=2% of identities, 0 at >=20%.
    result = round(max(0.0, min(100.0, 100.0 * (0.20 - share) / (0.20 - 0.02))), 4)
    return [
        EvidenceRecord(
            check_id="SE-005",
            pillar_key="security",
            result=result,
            measured={"admin_holders": len(holders), "identities": total_identities, "share": round(share, 4)},
            rationale=(
                f"{len(holders)} of {total_identities} identities ({share:.1%}) hold account-admin-class "
                "privilege. Broad admin holding makes every other control advisory, and gives any "
                "agent impersonating those identities unbounded blast radius."
            ),
            severity=severity_for(result),
            failing_targets=holders[:200],
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check("SE-006", title="Audit logging and retention", pillar="security", requires={"audit_config"})
def audit_retention(estate: Estate) -> list[EvidenceRecord]:
    """Audit must be enabled and retained long enough to reconstruct an incident."""
    programs = estate.governance_programs
    if not programs:
        return []
    enabled = [p for p in programs if p.audit_logging_enabled]
    retention = [p.audit_retention_days for p in programs if p.audit_logging_enabled]
    coverage = pct(len(enabled), len(programs))
    if retention:
        retention_score = min(100.0, 100.0 * (sum(retention) / len(retention)) / AUDIT_RETENTION_TARGET_DAYS)
    else:
        retention_score = 0.0
    result = round(0.6 * coverage + 0.4 * retention_score, 4)
    failing = [p.tool for p in programs if not p.audit_logging_enabled]
    failing += [
        f"{p.tool} (retention {p.audit_retention_days}d < {AUDIT_RETENTION_TARGET_DAYS}d)"
        for p in programs
        if p.audit_logging_enabled and p.audit_retention_days < AUDIT_RETENTION_TARGET_DAYS
    ]
    return [
        EvidenceRecord(
            check_id="SE-006",
            pillar_key="security",
            result=result,
            measured={
                "sources_with_audit": len(enabled),
                "sources": len(programs),
                "mean_retention_days": round(sum(retention) / len(retention), 1) if retention else 0,
                "target_retention_days": AUDIT_RETENTION_TARGET_DAYS,
            },
            rationale=(
                f"{len(enabled)} of {len(programs)} evidence sources have audit logging enabled, with a "
                f"mean retention of {(sum(retention) / len(retention)) if retention else 0:.0f} days against a "
                f"{AUDIT_RETENTION_TARGET_DAYS}-day target. Score blends coverage (60%) and retention (40%)."
            ),
            severity=severity_for(result),
            failing_targets=failing,
        )
    ]
