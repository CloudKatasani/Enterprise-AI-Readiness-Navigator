"""Request models for the API.

Responses are assembled by the dashboard/serialization layer as plain dicts, so
one serialization contract serves the API, the exports and the tests. Request
bodies are typed here because that is where validation earns its keep.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConnectorSpec(BaseModel):
    connector: str = Field(description="Registered connector key, e.g. 'snowflake'")
    config: dict[str, Any] = Field(default_factory=dict)


class TenantCreate(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    name: str
    industry: str = "unspecified"
    size_band: str = "unspecified"


class AssessmentRun(BaseModel):
    tenant_key: str
    connectors: list[ConnectorSpec] = Field(default_factory=lambda: [ConnectorSpec(connector="demo")])
    rubric_version: str | None = None
    label: str = ""
    generate_advice: bool = True


class EvidenceReview(BaseModel):
    decision: Literal["accepted", "rejected"]
    reviewer: str
    note: str | None = None


class RecommendationReview(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer: str
    note: str | None = None


class SimulationRequest(BaseModel):
    targets: dict[str, float] = Field(
        description="check_id -> target result (0-100) to simulate",
        json_schema_extra={"example": {"SE-002": 100, "MD-001": 90}},
    )


class QuestionnaireSubmission(BaseModel):
    tenant_key: str
    responses: list["QuestionnaireAnswer"]


class QuestionnaireAnswer(BaseModel):
    question_id: str
    question: str
    answer: str
    numeric_answer: float | None = None
    respondent: str | None = None


class SamplingAuthorizationCreate(BaseModel):
    tenant_key: str
    dataset_urn: str
    authorized_by: str
    justification: str = Field(min_length=10)
    expires_in_days: int = Field(default=30, ge=1, le=365)


QuestionnaireSubmission.model_rebuild()
