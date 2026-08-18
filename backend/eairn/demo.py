"""Live demo runner: configure an estate, run the full pipeline, show the result.

A demo audience does not want to read about the pipeline; they want to choose
their own platform and tooling, press a button, and see what the assessment says
about an estate shaped like theirs. This module is that button.

It is a thin, honest wrapper: the run is the *same* `run_assessment` the product
uses for a real harvest -- same checks, same rubric, same caps, same snapshot
hash. Only the connector differs, and it announces itself as synthetic in the
provenance every view reads. Nothing here can produce a score that the engine
would not have produced from the same evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from eairn.advisor import AdvisorInput, draft_executive_narrative
from eairn.config import get_settings
from eairn.connectors.profiles import (
    DQ_TOOL_CATALOG,
    GOVERNANCE_TOOL_CATALOG,
    INDUSTRY_PROFILES,
    MATURITY_PROFILES,
    PLATFORM_CATALOG,
    SCOPE_CATALOG,
    DemoOption,
    option_keys,
)
from eairn.dashboard import industry_label, portfolio
from eairn.models import Assessment, Evidence, Recommendation, Score, Tenant
from eairn.pipeline import run_assessment

#: Demo tenants are namespaced so a live demo can never overwrite a seeded
#: reference estate, and so they can be recognised in the portfolio.
DEMO_PREFIX = "demo-"

SIZE_BANDS: tuple[DemoOption, ...] = (
    DemoOption("enterprise", "Enterprise", "Large estate; Tier-1 assets dominate the denominators"),
    DemoOption("mid_market", "Mid-market", "Smaller estate, same bar"),
)

#: Maturity is the honest lever in a demo: it decides how far the governance
#: programme has actually got, and therefore what the checks will find.
MATURITY_NOTES = {
    "leading": "Governance complete on Tier-1, agent controls in production",
    "advancing": "Tier-1 governed, agent and RAG controls partially rolled out",
    "emerging": "Programme underway, coverage thin outside a few domains",
    "at_risk": "Little coverage; sensitive data largely unprotected",
}


def _options(catalog: tuple[DemoOption, ...]) -> list[dict[str, str]]:
    return [{"key": o.key, "label": o.label, "note": o.note} for o in catalog]


def portfolio_organisations(session: Session) -> list[dict[str, Any]]:
    """The assessed organizations, as the Organizations tab lists them.

    The demo form offers these so an audience picks a real, comparable estate
    rather than inventing a name. Running one produces a *separate* demo tenant:
    a reference estate is never overwritten by a demo, which is why the key is
    namespaced and the reference snapshot keeps its own history.
    """
    entries: list[dict[str, Any]] = []
    for industry in portfolio(session):
        for org in industry["organisations"]:
            entries.append(
                {
                    "key": org["tenant_key"],
                    "name": org["tenant"],
                    "industry": industry["industry"],
                    "industry_label": industry["industry_label"],
                    "size_band": org["size_band"],
                    "composite_score": org["composite_score"],
                    "grade": org["grade"],
                    "is_demo": org["tenant_key"].startswith(DEMO_PREFIX),
                }
            )
    return entries


def demo_options(session: Session | None = None) -> dict[str, Any]:
    """Everything the demo form may offer, straight from the profile catalogs.

    With a session, the assessed organizations are included so the form can be
    industry-first: choose an industry, then one of the organizations actually
    in it, then the size band.
    """
    return {
        "organisations": portfolio_organisations(session) if session is not None else [],
        "platforms": _options(PLATFORM_CATALOG),
        "governance_tools": _options(GOVERNANCE_TOOL_CATALOG),
        "dq_tools": _options(DQ_TOOL_CATALOG),
        "scopes": _options(SCOPE_CATALOG),
        "size_bands": _options(SIZE_BANDS),
        "industries": [
            {"key": key, "label": profile.label, "note": f"{len(profile.domains)} business domains"}
            for key, profile in sorted(INDUSTRY_PROFILES.items(), key=lambda kv: kv[1].label)
        ],
        "maturities": [
            {"key": key, "label": key.replace("_", "-").title(), "note": MATURITY_NOTES.get(key, profile.label)}
            for key, profile in MATURITY_PROFILES.items()
        ],
        "defaults": {
            "organisation": "Vantage Northwind Bank",
            "industry": "financial_services",
            "platform": "snowflake",
            "governance_tool": "collibra",
            "dq_tool": "monte_carlo",
            "maturity": "emerging",
            "size_band": "enterprise",
            "seed": 20260817,
            "scopes_off": [],
        },
    }


@dataclass
class DemoSpec:
    organisation: str
    industry: str = "financial_services"
    platform: str = "snowflake"
    governance_tool: str = "collibra"
    dq_tool: str = "monte_carlo"
    maturity: str = "emerging"
    size_band: str = "enterprise"
    seed: int = 20260817
    scopes_off: list[str] = field(default_factory=list)
    generate_advice: bool = True

    def validate(self) -> None:
        """Reject an unknown choice rather than silently falling back.

        A demo that quietly substituted Snowflake for a mistyped platform would
        show the audience numbers for an estate they did not ask for.
        """
        problems = []
        if not self.organisation.strip():
            problems.append("organisation name is required")
        if self.industry not in INDUSTRY_PROFILES:
            problems.append(f"unknown industry {self.industry!r}")
        if self.maturity not in MATURITY_PROFILES:
            problems.append(f"unknown maturity {self.maturity!r}")
        if self.platform not in option_keys(PLATFORM_CATALOG):
            problems.append(f"unknown platform {self.platform!r}")
        if self.governance_tool not in option_keys(GOVERNANCE_TOOL_CATALOG):
            problems.append(f"unknown governance tool {self.governance_tool!r}")
        if self.dq_tool not in option_keys(DQ_TOOL_CATALOG):
            problems.append(f"unknown data quality tool {self.dq_tool!r}")
        if self.size_band not in option_keys(SIZE_BANDS):
            problems.append(f"unknown size band {self.size_band!r}")
        unknown_scopes = set(self.scopes_off) - option_keys(SCOPE_CATALOG)
        if unknown_scopes:
            problems.append(f"unknown scope(s) {sorted(unknown_scopes)}")
        if problems:
            raise ValueError("; ".join(problems))

    @property
    def tenant_key(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.organisation.lower()).strip("-") or "estate"
        return f"{DEMO_PREFIX}{slug}"[:64]

    @property
    def email_domain(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "", self.organisation.lower()) or "estate"
        return f"{slug[:24]}.example"

    def connector_config(self) -> dict[str, Any]:
        return {
            "industry": self.industry,
            "maturity": self.maturity,
            "platform": self.platform,
            "governance_tool": self.governance_tool,
            "dq_tool": self.dq_tool,
            "capabilities_off": list(self.scopes_off),
            "seed": self.seed,
            "email_domain": self.email_domain,
        }


def _reset_tenant_history(session: Session, tenant: Tenant) -> None:
    """A demo tenant keeps one snapshot: the run the audience just watched.

    Reference estates accumulate snapshots so the trend line means something.
    A demo re-run of the same name is a re-do, not history, and leaving the old
    ones would put a meaningless trend on the executive view.
    """
    previous = list(session.scalars(select(Assessment).where(Assessment.tenant_id == tenant.id)))
    for assessment in previous:
        for model in (Score, Evidence, Recommendation):
            for row in session.scalars(select(model).where(model.assessment_id == assessment.id)):
                session.delete(row)
        session.delete(assessment)
    session.flush()


def _display_name(session: Session, spec: DemoSpec) -> str:
    """Name the demo estate so it cannot be mistaken for the reference one.

    The demo form offers the assessed organizations by name, so a run is often
    named after an estate that already exists. That run is a *separate* tenant
    with its own snapshot -- the reference assessment is untouched -- and two
    identically named rows in the portfolio would hide that. A freely typed name
    keeps whatever the user typed.
    """
    name = spec.organisation.strip()
    clash = session.scalar(
        select(Tenant).where(Tenant.name == name, Tenant.key != spec.tenant_key)
    )
    return f"{name} (demo run)" if clash is not None else name


def run_demo(session: Session, spec: DemoSpec) -> Assessment:
    """Harvest -> evaluate -> score -> recommend -> narrate, on a synthetic estate."""
    spec.validate()

    tenant = session.scalar(select(Tenant).where(Tenant.key == spec.tenant_key))
    display_name = _display_name(session, spec)
    if tenant is None:
        tenant = Tenant(key=spec.tenant_key, name=display_name)
        session.add(tenant)
        session.flush()
    else:
        _reset_tenant_history(session, tenant)
    tenant.name = display_name
    tenant.industry = spec.industry
    tenant.size_band = spec.size_band

    assessment = run_assessment(
        session,
        tenant,
        [("demo", spec.connector_config())],
        label=(
            f"Live demo — {industry_label(spec.industry)} on "
            f"{spec.platform} with {spec.governance_tool}"
        ),
    )

    if spec.generate_advice:
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
        session.flush()

    return assessment


def advisor_mode() -> str:
    """Whether the narrative on a demo run will be model-written or templated."""
    return "model" if get_settings().anthropic_api_key else "template"
