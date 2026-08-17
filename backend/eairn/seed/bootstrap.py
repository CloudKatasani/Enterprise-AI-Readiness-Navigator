"""Bootstrap the demo portfolio: rubric, cohorts, tenants and one assessment each.

    python -m eairn.seed.bootstrap                 # the whole portfolio
    python -m eairn.seed.bootstrap --only northwind

Thirteen sample organisations across six industries, each with its own industry
and maturity profile, so the Portal can be evaluated against more than one shape
of estate. Idempotent: re-running replaces each tenant's canonical data and adds
a new snapshot, which is also how the trend line gets its second point.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import select

from eairn.advisor import AdvisorInput, draft_executive_narrative
from eairn.benchmarks import install_cohorts
from eairn.config import get_settings
from eairn.db import init_db, session_scope
from eairn.models import Assessment, Evidence, QuestionnaireResponse, Recommendation, Score, Tenant
from eairn.pipeline import run_assessment
from eairn.rubric import get_rubric, install_rubric


@dataclass(frozen=True)
class SampleOrg:
    key: str
    name: str
    industry: str
    maturity: str
    size_band: str
    seed: int
    email_domain: str


# Sample estates. The maturity mix is deliberate: every industry shows at least
# two different stages of a governance programme, so a reader can see what the
# same eight pillars look like at different levels of investment.
SAMPLE_ORGS: tuple[SampleOrg, ...] = (
    # Financial services
    SampleOrg("northwind", "Northwind Financial", "financial_services", "emerging", "enterprise", 20260817, "northwind.example"),
    SampleOrg("calder-voss", "Calder & Voss Capital", "financial_services", "leading", "enterprise", 20260901, "caldervoss.example"),
    SampleOrg("basalt-mutual", "Basalt Mutual", "financial_services", "at_risk", "mid_market", 20261014, "basaltmutual.example"),
    # Telecommunications
    SampleOrg("meridian-telecom", "Meridian Telecom", "telecommunications", "advancing", "enterprise", 20260222, "meridiantel.example"),
    SampleOrg("northbeam-wireless", "Northbeam Wireless", "telecommunications", "emerging", "enterprise", 20260311, "northbeam.example"),
    # Retail
    SampleOrg("harborline-retail", "Harborline Retail Group", "retail", "emerging", "enterprise", 20260405, "harborline.example"),
    SampleOrg("tessella-markets", "Tessella Markets", "retail", "advancing", "mid_market", 20260519, "tessella.example"),
    # Utilities
    SampleOrg("anvil-grid", "Anvil Grid Utilities", "utilities", "at_risk", "enterprise", 20260628, "anvilgrid.example"),
    SampleOrg("cascadia-power", "Cascadia Water & Power", "utilities", "emerging", "enterprise", 20260712, "cascadiapower.example"),
    # Technology
    SampleOrg("loftware", "Loftware Technologies", "technology", "leading", "enterprise", 20260130, "loftware.example"),
    SampleOrg("quanta-cloud", "Quanta Cloud Systems", "technology", "advancing", "mid_market", 20260208, "quantacloud.example"),
    # Healthcare
    SampleOrg("silverpine-health", "Silverpine Health System", "healthcare", "advancing", "enterprise", 20260924, "silverpine.example"),
    SampleOrg("arbor-clinical", "Arbor Clinical Network", "healthcare", "emerging", "mid_market", 20261102, "arborclinical.example"),
)

# Self-reported answers for the flagship tenant. Q-GOV-04 deliberately overstates
# lineage coverage -- the contradiction is what check GV-009 exists to catch.
DEMO_QUESTIONNAIRE = [
    ("Q-GOV-02", "About 85% of critical datasets have a named owner.", 85.0),
    ("Q-GOV-04", "We have full column-level lineage across Tier-1.", 95.0),
    ("Q-QS-04", "Business users query in natural language; acceptance is around 70%.", 70.0),
]


def _seed_questionnaire(session, tenant: Tenant) -> None:
    from eairn.questionnaire import question_index

    questions = question_index()
    existing = {
        r.question_id
        for r in session.scalars(
            select(QuestionnaireResponse).where(QuestionnaireResponse.tenant_id == tenant.id)
        )
    }
    for question_id, answer, numeric in DEMO_QUESTIONNAIRE:
        if question_id in existing:
            continue
        session.add(
            QuestionnaireResponse(
                tenant_id=tenant.id,
                question_id=question_id,
                question=questions[question_id]["question"],
                answer=answer,
                numeric_answer=numeric,
                respondent=f"cdo@{tenant.key}.example",
            )
        )
    session.flush()


def assess_org(session, org: SampleOrg, label: str) -> Assessment:
    tenant = session.scalar(select(Tenant).where(Tenant.key == org.key))
    if tenant is None:
        tenant = Tenant(
            key=org.key, name=org.name, industry=org.industry, size_band=org.size_band
        )
        session.add(tenant)
        session.flush()

    if org.key == "northwind":
        _seed_questionnaire(session, tenant)

    assessment = run_assessment(
        session,
        tenant,
        [
            (
                "demo",
                {
                    "industry": org.industry,
                    "maturity": org.maturity,
                    "seed": org.seed,
                    "email_domain": org.email_domain,
                },
            )
        ],
        label=label,
    )

    scores = list(session.scalars(select(Score).where(Score.assessment_id == assessment.id)))
    evidence = list(session.scalars(select(Evidence).where(Evidence.assessment_id == assessment.id)))
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
    return assessment


def bootstrap(label: str = "Baseline assessment", only: str | None = None) -> list[str]:
    settings = get_settings()
    init_db()
    snapshots: list[str] = []
    orgs = [o for o in SAMPLE_ORGS if only is None or o.key == only]
    if not orgs:
        raise SystemExit(
            f"unknown org {only!r}; available: {', '.join(o.key for o in SAMPLE_ORGS)}"
        )

    with session_scope() as session:
        if get_rubric(session, settings.default_rubric_version) is None:
            install_rubric(session, settings.default_rubric_version)
        install_cohorts(session)

    header = f"{'Organisation':28} {'Industry':22} {'Composite':>9}  {'Grade':13} {'ARI':>5} {'RRI':>5}"
    print(header)
    print("-" * len(header))
    for org in orgs:
        with session_scope() as session:
            assessment = assess_org(session, org, label)
            snapshots.append(assessment.snapshot_id)
            print(
                f"{org.name:28} {org.industry:22} {assessment.composite_score:9.1f}  "
                f"{assessment.grade:13} {assessment.ari_score:5.1f} {assessment.rri_score:5.1f}"
            )
    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the EAIRN demo portfolio")
    parser.add_argument("--label", default="Baseline assessment")
    parser.add_argument("--only", help="Seed a single organisation by key")
    args = parser.parse_args()
    bootstrap(args.label, args.only)


if __name__ == "__main__":
    main()
