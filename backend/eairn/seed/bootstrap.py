"""Bootstrap a demo estate: rubric, cohorts, tenant, questionnaire and one assessment.

    python -m eairn.seed.bootstrap

Idempotent: re-running replaces the tenant's canonical data and adds a new
snapshot, which is also how the trend line in the executive view gets its second
point.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from eairn.advisor import AdvisorInput, draft_executive_narrative
from eairn.benchmarks import install_cohorts
from eairn.config import get_settings
from eairn.db import init_db, session_scope
from eairn.models import Assessment, Evidence, QuestionnaireResponse, Recommendation, Score, Tenant
from eairn.pipeline import run_assessment
from eairn.rubric import get_rubric, install_rubric

DEMO_TENANT = {
    "key": "northwind",
    "name": "Northwind Financial",
    "industry": "financial_services",
    "size_band": "enterprise",
}

# Self-reported answers. Q-GOV-04 deliberately overstates lineage coverage --
# the contradiction is what check GV-009 exists to catch.
DEMO_QUESTIONNAIRE = [
    ("Q-GOV-02", "About 85% of critical datasets have a named owner.", 85.0),
    ("Q-GOV-04", "We have full column-level lineage across Tier-1.", 95.0),
    ("Q-QS-04", "Business users query in natural language; acceptance is around 70%.", 70.0),
]


def bootstrap(label: str = "Baseline assessment") -> str:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        if get_rubric(session, settings.default_rubric_version) is None:
            install_rubric(session, settings.default_rubric_version)
        install_cohorts(session)

        tenant = session.scalar(select(Tenant).where(Tenant.key == DEMO_TENANT["key"]))
        if tenant is None:
            tenant = Tenant(**DEMO_TENANT)
            session.add(tenant)
            session.flush()

        from eairn.questionnaire import question_index

        questions = question_index()
        existing_ids = {
            r.question_id
            for r in session.scalars(
                select(QuestionnaireResponse).where(QuestionnaireResponse.tenant_id == tenant.id)
            )
        }
        for question_id, answer, numeric in DEMO_QUESTIONNAIRE:
            if question_id in existing_ids:
                continue
            session.add(
                QuestionnaireResponse(
                    tenant_id=tenant.id,
                    question_id=question_id,
                    question=questions[question_id]["question"],
                    answer=answer,
                    numeric_answer=numeric,
                    respondent="cdo@northwind.example",
                )
            )
        session.flush()

        assessment = run_assessment(session, tenant, [("demo", {})], label=label)

        scores = list(session.scalars(select(Score).where(Score.assessment_id == assessment.id)))
        evidence = list(
            session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id))
        )
        recommendations = list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.assessment_id == assessment.id)
                .order_by(Recommendation.composite_impact.desc())
            )
        )
        session.add(
            draft_executive_narrative(
                AdvisorInput(
                    assessment=assessment,
                    scores=scores,
                    evidence=evidence,
                    recommendations=recommendations,
                )
            )
        )

        print(f"tenant           : {tenant.name} ({tenant.key})")
        print(f"snapshot         : {assessment.snapshot_id}")
        print(f"rubric           : v{assessment.rubric_version}")
        print(f"composite        : {assessment.composite_score:.1f} ({assessment.grade})")
        print(f"ARI              : {assessment.ari_score:.1f} ({assessment.ari_grade})")
        print(f"RRI              : {assessment.rri_score:.1f} ({assessment.rri_grade})")
        print(f"evidence records : {len(evidence)}")
        print(f"pending review   : {assessment.stats['pending_review']}")
        print(f"caps applied     : {[c['override'] for c in assessment.stats['caps_applied']]}")
        print(f"recommendations  : {len(recommendations)}")
        print(f"snapshot hash    : {assessment.snapshot_hash}")
        return assessment.snapshot_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the EAIRN demo estate")
    parser.add_argument("--label", default="Baseline assessment")
    args = parser.parse_args()
    bootstrap(args.label)


if __name__ == "__main__":
    main()
