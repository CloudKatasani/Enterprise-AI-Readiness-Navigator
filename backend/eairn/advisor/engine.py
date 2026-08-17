"""AI Advisor.

Drafts executive narratives and roadmap summaries from an assessment snapshot.
Two hard constraints, both from the blueprint:

* **Grounded strictly in the snapshot.** The advisor is handed a compact payload
  of scores, evidence records and draft recommendations, and is told to cite the
  evidence IDs it used. It is never given the customer's data, only the
  assessment's own facts.
* **Every generated artefact stores its prompt, citations, confidence and
  reviewer decision.** Narratives land in ``draft`` status; a human approves.

Without an API key the advisor produces a deterministic, evidence-grounded
narrative from a template, so the product is fully functional offline and the
tests do not depend on a network call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from eairn.config import get_settings
from eairn.models import Assessment, AdvisorNarrative, Evidence, Recommendation, Score

SYSTEM_PROMPT = """\
You are the EAIRN advisor. You write short, defensible executive narratives about an \
enterprise's readiness for GenAI, agentic AI and RAG, using ONLY the assessment snapshot \
you are given.

Rules you must follow:
1. Every factual claim must come from the snapshot. Do not invent numbers, systems, \
vendors, dates or people.
2. Cite the evidence IDs that support each claim, using the integer IDs from the payload.
3. If the snapshot does not support a claim the reader would expect, say what is not \
measured rather than estimating it.
4. Hard-blocker caps are the most important thing an executive needs to understand: if a \
cap is applied, lead with what it blocks and what clears it.
5. Write for a CDO or CDAO. No preamble, no marketing language, no bullet-point padding. \
Four short paragraphs at most.\
"""

NARRATIVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "narrative": {
            "type": "string",
            "description": "The executive narrative, 4 short paragraphs at most.",
        },
        "citations": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Evidence IDs supporting the claims made, from the payload.",
        },
        "confidence": {
            "type": "number",
            "description": "0-1 confidence that the narrative is fully supported by the snapshot.",
        },
    },
    "required": ["narrative", "citations", "confidence"],
    "additionalProperties": False,
}


@dataclass
class AdvisorInput:
    assessment: Assessment
    scores: Sequence[Score]
    evidence: Sequence[Evidence]
    recommendations: Sequence[Recommendation]
    cohort: dict[str, Any] | None = None


def build_payload(data: AdvisorInput, *, max_evidence: int = 40) -> dict[str, Any]:
    """Compact, fully-cited snapshot payload. Metadata only -- never row data."""
    assessment = data.assessment
    pillars = [
        {
            "key": s.key,
            "name": s.name,
            "score": s.score,
            "uncapped_score": s.raw_score,
            "weight": s.weight,
            "capped_by": s.capped_by,
        }
        for s in data.scores
        if s.scope == "pillar"
    ]
    # Weakest-first: the executive question is always "what is holding us back".
    ranked_evidence = sorted(
        data.evidence, key=lambda e: (e.result, -len(e.failing_targets or []))
    )[:max_evidence]
    return {
        "tenant": assessment.tenant.name if assessment.tenant else "tenant",
        "snapshot_id": assessment.snapshot_id,
        "rubric_version": assessment.rubric_version,
        "harvested_at": assessment.harvested_at.isoformat() if assessment.harvested_at else None,
        "composite_score": assessment.composite_score,
        "grade": assessment.grade,
        "ari": {"score": assessment.ari_score, "grade": assessment.ari_grade},
        "rri": {"score": assessment.rri_score, "grade": assessment.rri_grade},
        "caps_applied": (assessment.stats or {}).get("caps_applied", []),
        "unmeasured_criteria": (assessment.stats or {}).get("unmeasured_criteria", []),
        "pillars": pillars,
        "cohort": data.cohort,
        "evidence": [
            {
                "id": e.id,
                "check_id": e.check_id,
                "title": e.check_title,
                "pillar": e.pillar_key,
                "result": e.result,
                "confidence": e.confidence,
                "severity": e.severity,
                "status": e.status,
                "failing_count": len(e.failing_targets or []),
                "rationale": e.rationale,
            }
            for e in ranked_evidence
        ],
        "recommendations": [
            {
                "playbook_id": r.playbook_id,
                "title": r.title,
                "horizon": r.horizon,
                "effort_days": r.effort_days,
                "composite_impact": r.composite_impact,
                "unblocks": r.unblocks,
                "evidence_ids": r.evidence_ids,
            }
            for r in data.recommendations[:10]
        ],
    }


def draft_executive_narrative(data: AdvisorInput) -> AdvisorNarrative:
    """Draft an executive narrative. Falls back to a template with no API key."""
    settings = get_settings()
    payload = build_payload(data)
    if not settings.anthropic_api_key:
        return _template_narrative(data, payload)
    try:
        return _llm_narrative(data, payload, settings)
    except Exception as exc:  # noqa: BLE001 - an advisor outage must not fail an assessment
        narrative = _template_narrative(data, payload)
        narrative.body += (
            f"\n\n[Advisor note: the language model was unavailable ({exc.__class__.__name__}), "
            "so this narrative was generated from the deterministic template. The numbers and "
            "citations above are drawn from the snapshot either way.]"
        )
        return narrative


def _llm_narrative(data: AdvisorInput, payload: dict[str, Any], settings) -> AdvisorNarrative:
    import anthropic  # imported lazily so the package stays an optional extra

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_content = (
        "Write the executive narrative for this assessment snapshot.\n\n"
        "```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"
    )
    request = {
        "model": settings.advisor_model,
        "max_tokens": settings.advisor_max_tokens,
        "system": SYSTEM_PROMPT,
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": settings.advisor_effort,
            "format": {"type": "json_schema", "schema": NARRATIVE_SCHEMA},
        },
        "messages": [{"role": "user", "content": user_content}],
    }
    response = client.messages.create(**request)

    if response.stop_reason == "refusal":
        raise RuntimeError("advisor request was declined by the model's safety classifiers")

    text = next((b.text for b in response.content if b.type == "text"), "")
    parsed = json.loads(text)
    valid_ids = {e["id"] for e in payload["evidence"] if e["id"] is not None}
    citations = [int(c) for c in parsed.get("citations", []) if int(c) in valid_ids]

    return AdvisorNarrative(
        assessment_id=data.assessment.id,
        kind="executive_summary",
        body=parsed["narrative"].strip(),
        citations=citations,
        generator="llm",
        model=response.model,
        prompt={
            "system": SYSTEM_PROMPT,
            "user": user_content,
            "model": settings.advisor_model,
            "effort": settings.advisor_effort,
            "schema": NARRATIVE_SCHEMA,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        },
        confidence=float(parsed.get("confidence", 0.8)),
        status="draft",
    )


def _template_narrative(data: AdvisorInput, payload: dict[str, Any]) -> AdvisorNarrative:
    """Deterministic fallback. Same grounding rules, no model."""
    assessment = data.assessment
    pillars = sorted(payload["pillars"], key=lambda p: p["score"])
    weakest = pillars[:3]
    caps = payload["caps_applied"]
    citations: list[int] = []

    lines = [
        f"{payload['tenant']} scores {assessment.composite_score:.1f}/100 "
        f"({assessment.grade}) for AI readiness under rubric v{assessment.rubric_version}, "
        f"from snapshot {assessment.snapshot_id}. The Agent Readiness Index stands at "
        f"{_fmt(assessment.ari_score)} ({assessment.ari_grade or 'not scored'}) and the RAG "
        f"Readiness Index at {_fmt(assessment.rri_score)} ({assessment.rri_grade or 'not scored'})."
    ]

    if caps:
        cap_sentences = []
        for cap in caps:
            cap_sentences.append(
                f"{cap['scope']} is capped at {cap['cap_value']:.0f} (arithmetic score "
                f"{cap['uncapped_score']:.1f}) by {cap['check_id']} with "
                f"{cap['failing_targets']} failing target(s)"
            )
        lines.append(
            "Hard blockers are the binding constraint: "
            + "; ".join(cap_sentences)
            + ". These caps hold regardless of progress elsewhere, so they are the first thing "
            "to clear."
        )

    weakest_bits = []
    for pillar in weakest:
        supporting = [
            e for e in payload["evidence"] if e["pillar"] == pillar["key"] and e["id"] is not None
        ][:2]
        citations.extend(e["id"] for e in supporting)
        detail = supporting[0]["rationale"].split(".")[0] if supporting else "no supporting evidence"
        weakest_bits.append(f"{pillar['name']} at {pillar['score']:.0f} ({detail})")
    if weakest_bits:
        lines.append("The weakest pillars are " + "; ".join(weakest_bits) + ".")

    approved_first = [r for r in payload["recommendations"][:3]]
    if approved_first:
        plan = "; ".join(
            f"{r['title']} ({r['horizon'].replace('_', ' ')}, ~{r['effort_days']:.0f} days, "
            f"projected composite {r['composite_impact']:+.1f})"
            for r in approved_first
        )
        lines.append(
            "The highest-return sequence by simulated score impact per effort day is: " + plan + "."
        )

    unmeasured = payload["unmeasured_criteria"]
    if unmeasured:
        lines.append(
            f"{len(unmeasured)} rubric criteria were not measured in this run "
            f"({', '.join(unmeasured[:5])}{'...' if len(unmeasured) > 5 else ''}); they are "
            "reported as unmeasured rather than scored as zero, and closing them requires "
            "additional connector coverage."
        )

    return AdvisorNarrative(
        assessment_id=assessment.id,
        kind="executive_summary",
        body="\n\n".join(lines),
        citations=sorted(set(citations)),
        generator="template",
        model=None,
        prompt={"generator": "deterministic_template", "payload_keys": sorted(payload)},
        confidence=1.0,
        status="draft",
    )


def _fmt(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "not scored"
