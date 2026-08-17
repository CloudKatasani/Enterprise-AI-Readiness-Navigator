"""Agent Readiness checks (AG-xxx).

Five dimensions -- discover, trust, explain, act safely, audit -- plus the
compositional entitlement problem that single-tool RBAC does not see.
"""

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


def _no_agents_record(check_id: str, title: str, rationale: str) -> EvidenceRecord:
    """No deployed agents is not a pass -- it is an unmeasurable dimension."""
    return EvidenceRecord(
        check_id=check_id,
        check_title=title,
        pillar_key="agent_readiness",
        result=0.0,
        measured={"agents": 0},
        rationale=rationale,
        severity="medium",
        confidence=CONFIDENCE_DERIVED,
    )


@check("AG-001", title="Machine-readable metadata surface", pillar="agent_readiness", requires={"datasets"})
def discover_surface(estate: Estate) -> list[EvidenceRecord]:
    """What fraction of Tier-1 assets an agent could select correctly from metadata alone."""
    tier1 = estate.tier1
    if not tier1:
        return []
    discoverable, failing = 0, []
    for dataset in tier1:
        described = bool(dataset.description)
        columns_described = (
            sum(1 for c in dataset.columns if c.description) >= 0.8 * len(dataset.columns)
            if dataset.columns
            else False
        )
        in_semantic_layer = any(
            dataset.domain and dataset.domain in (m.covered_domains or [])
            for m in estate.semantic_models
        )
        if described and (columns_described or in_semantic_layer):
            discoverable += 1
        else:
            reasons = []
            if not described:
                reasons.append("no table description")
            if not columns_described:
                reasons.append("<80% columns described")
            if not in_semantic_layer:
                reasons.append("no semantic model coverage")
            failing.append(f"{dataset.urn} ({'; '.join(reasons)})")
    return [
        ratio_evidence(
            "AG-001",
            "agent_readiness",
            title="Machine-readable metadata surface",
            numerator=discoverable,
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) expose enough machine-readable context "
                "(table description plus either column descriptions or semantic-model coverage) for "
                "an agent to select them deliberately rather than by name similarity."
            ),
            failing=failing,
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check("AG-002", title="Runtime-queryable trust signals", pillar="agent_readiness", requires={"datasets"})
def runtime_trust(estate: Estate) -> list[EvidenceRecord]:
    """Can an agent ask, at query time, whether this data is fresh, monitored and certified?"""
    tier1 = estate.tier1
    if not tier1:
        return []
    signalled, failing = 0, []
    for dataset in tier1:
        monitored = bool(estate.monitors_for(dataset.urn))
        if dataset.certified and monitored:
            signalled += 1
        else:
            missing = []
            if not dataset.certified:
                missing.append("no certification flag")
            if not monitored:
                missing.append("no DQ monitor to query")
            failing.append(f"{dataset.urn} ({'; '.join(missing)})")
    agents_with_signals = [a for a in estate.agents if a.runtime_trust_signals]
    record = ratio_evidence(
        "AG-002",
        "agent_readiness",
        title="Runtime-queryable trust signals",
        numerator=signalled,
        denominator=len(tier1),
        unit="Tier-1 datasets",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) expose both a certification flag and a "
            "queryable DQ status. An agent that cannot check freshness at runtime will answer "
            "confidently from stale data."
        ),
        failing=failing,
        confidence=CONFIDENCE_DERIVED,
        extra={"agents_consuming_trust_signals": len(agents_with_signals)},
    )
    if estate.agents and not agents_with_signals:
        record.result = round(record.result * 0.5, 4)
        record.severity = severity_for(record.result)
        record.rationale += (
            " No deployed agent consumes these signals today, so the available half of the signal "
            "is not reaching the runtime; the score is halved accordingly."
        )
    return [record]


@check("AG-003", title="Lineage and definition traceability", pillar="agent_readiness", requires={"lineage"})
def explainability(estate: Estate) -> list[EvidenceRecord]:
    """Can an agent cite where an answer came from?"""
    tier1 = estate.tier1
    if not tier1:
        return []
    traceable, failing = 0, []
    certified_kpi_names = {k.kpi_name for k in estate.kpi_definitions if k.certified}
    for dataset in tier1:
        has_lineage = bool(estate.upstream_of(dataset.urn))
        has_definitions = bool(dataset.glossary_terms) or bool(certified_kpi_names)
        if has_lineage and has_definitions:
            traceable += 1
        else:
            failing.append(dataset.urn)
    return [
        ratio_evidence(
            "AG-003",
            "agent_readiness",
            title="Lineage and definition traceability",
            numerator=traceable,
            denominator=len(tier1),
            unit="Tier-1 datasets",
            rationale_template=(
                "{numerator} of {denominator} {unit} ({pct}%) can support a citation: resolvable "
                "lineage plus a queryable definition. Citations are what make an agent answer "
                "auditable instead of merely plausible."
            ),
            failing=failing,
            confidence=CONFIDENCE_DERIVED,
        )
    ]


@check("AG-004", title="Per-agent scoped entitlements", pillar="agent_readiness", requires={"agents"})
def scoped_entitlements(estate: Estate) -> list[EvidenceRecord]:
    """Distinct identity plus scoped roles -- no shared superuser."""
    agents = estate.agents
    if not agents:
        return [
            _no_agents_record(
                "AG-004",
                "Per-agent scoped entitlements",
                "No agent identities were harvested. Agent entitlement posture cannot be evidenced, "
                "so this dimension scores zero until an agent estate exists to assess.",
            )
        ]
    scoped = [a for a in agents if a.scoped_roles and a.identity_kind == "distinct"]
    failing = []
    for agent in agents:
        if agent in scoped:
            continue
        reasons = []
        if agent.identity_kind != "distinct":
            reasons.append(f"identity is {agent.identity_kind}")
        if not agent.scoped_roles:
            reasons.append("no per-agent scoped role")
        failing.append(f"{agent.name} ({'; '.join(reasons)})")
    record = ratio_evidence(
        "AG-004",
        "agent_readiness",
        title="Per-agent scoped entitlements",
        numerator=len(scoped),
        denominator=len(agents),
        unit="agents",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) run under a distinct identity with a scoped "
            "role. An agent sharing a human or service identity inherits that identity's full blast "
            "radius and is indistinguishable from it in the audit trail."
        ),
        failing=failing,
    )
    if failing:
        record.severity = "critical" if record.result < 50 else "high"
    return [record]


@check("AG-005", title="Approval gates on write actions", pillar="agent_readiness", requires={"agents"})
def write_gates(estate: Estate) -> list[EvidenceRecord]:
    """Write-capable agents need a human approval gate."""
    writers = [a for a in estate.agents if a.write_actions]
    if not estate.agents:
        return [
            _no_agents_record(
                "AG-005",
                "Approval gates on write actions",
                "No agent identities were harvested, so write-action controls cannot be evidenced.",
            )
        ]
    if not writers:
        return [
            EvidenceRecord(
                check_id="AG-005",
                pillar_key="agent_readiness",
                result=100.0,
                measured={"write_capable_agents": 0, "agents": len(estate.agents)},
                rationale=(
                    "No harvested agent holds write capability, so no approval gate is required. This "
                    "is a full pass today and must be re-evaluated the moment write actions are enabled."
                ),
                confidence=CONFIDENCE_DECLARED,
            )
        ]
    gated = [a for a in writers if a.write_approval_gate]
    record = ratio_evidence(
        "AG-005",
        "agent_readiness",
        title="Approval gates on write actions",
        numerator=len(gated),
        denominator=len(writers),
        unit="write-capable agents",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) require human approval before a write "
            "action executes. An ungated write-capable agent can change production state without a "
            "reviewable decision."
        ),
        failing=[a.name for a in writers if not a.write_approval_gate],
    )
    if record.failing_targets:
        record.severity = "critical"
    return [record]


@check("AG-006", title="Attributable, replayable action trails", pillar="agent_readiness", requires={"agents"})
def action_audit(estate: Estate) -> list[EvidenceRecord]:
    """Hard blocker: agent actions must be attributable and replayable."""
    agents = estate.agents
    if not agents:
        return [
            _no_agents_record(
                "AG-006",
                "Attributable, replayable action trails",
                "No agent identities were harvested, so no action trail can be evidenced.",
            )
        ]
    audited = [a for a in agents if a.action_audit and a.replayable_trail and a.identity_kind == "distinct"]
    failing = []
    for agent in agents:
        if agent in audited:
            continue
        reasons = []
        if not agent.action_audit:
            reasons.append("actions not logged")
        if not agent.replayable_trail:
            reasons.append("trail not replayable to evidence and approval")
        if agent.identity_kind != "distinct":
            reasons.append("agent identity not distinct from human identities")
        failing.append(f"{agent.name} ({'; '.join(reasons)})")
    record = ratio_evidence(
        "AG-006",
        "agent_readiness",
        title="Attributable, replayable action trails",
        numerator=len(audited),
        denominator=len(agents),
        unit="agents",
        rationale_template=(
            "{numerator} of {denominator} {unit} ({pct}%) produce an attributable, replayable action "
            "trail (distinct identity, logged actions, action -> evidence -> approval chain "
            "reconstructable). Any gap triggers the Agent Readiness hard-blocker cap."
        ),
        failing=failing,
    )
    if failing:
        record.severity = "critical"
    return [record]


@check("AG-007", title="Compositional entitlement reconciliation", pillar="agent_readiness", requires={"agents"})
def compositional_control(estate: Estate) -> list[EvidenceRecord]:
    """Multi-tool agents can synthesise a disclosure no single tool permits.

    Scored conservatively: this failure mode has no settled industry control, so
    the check looks for the *capability* to detect it -- cross-tool entitlement
    reconciliation, inference-control policy on sensitive combinations, and
    logging sufficient to reconstruct a composed flow.
    """
    multi_tool = [a for a in estate.agents if len(a.tools or []) > 1]
    if not estate.agents:
        return [
            _no_agents_record(
                "AG-007",
                "Compositional entitlement reconciliation",
                "No agent identities were harvested, so compositional exposure cannot be assessed.",
            )
        ]
    if not multi_tool:
        return [
            EvidenceRecord(
                check_id="AG-007",
                pillar_key="agent_readiness",
                result=100.0,
                measured={"multi_tool_agents": 0, "agents": len(estate.agents)},
                rationale=(
                    "No harvested agent composes more than one tool, so there is no compositional "
                    "disclosure surface today. This becomes scoreable as soon as tool composition begins."
                ),
                confidence=CONFIDENCE_DERIVED,
            )
        ]
    controlled = [
        a for a in multi_tool if a.entitlement_reconciliation and a.inference_control_policy and a.action_audit
    ]
    failing = []
    for agent in multi_tool:
        if agent in controlled:
            continue
        reasons = []
        if not agent.entitlement_reconciliation:
            reasons.append("no cross-tool entitlement reconciliation")
        if not agent.inference_control_policy:
            reasons.append("no inference-control policy on sensitive combinations")
        if not agent.action_audit:
            reasons.append("composed data flow not reconstructable from logs")
        failing.append(f"{agent.name} [{', '.join(agent.tools or [])}] ({'; '.join(reasons)})")
    result = pct(len(controlled), len(multi_tool))
    return [
        EvidenceRecord(
            check_id="AG-007",
            pillar_key="agent_readiness",
            result=result,
            measured={"multi_tool_agents": len(multi_tool), "controlled": len(controlled)},
            rationale=(
                f"{len(controlled)} of {len(multi_tool)} multi-tool agents ({result:.1f}%) sit behind "
                "cross-tool entitlement reconciliation, an inference-control policy and logging that "
                "can reconstruct a composed flow. An agent combining individually-authorised tools can "
                "synthesise a disclosure that no single tool would permit, and single-tool RBAC will "
                "not see it."
            ),
            severity="critical" if result < 50 else severity_for(result),
            failing_targets=failing,
            confidence=CONFIDENCE_DERIVED,
        )
    ]
