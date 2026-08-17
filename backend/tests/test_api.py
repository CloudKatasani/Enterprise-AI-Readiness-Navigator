"""API surface tests: the paths the Portal actually calls."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eairn.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["row_sampling_enabled"] is False


def test_connector_catalog_publishes_permission_manifests(client: TestClient) -> None:
    connectors = client.get("/api/connectors").json()["connectors"]
    keys = {c["key"] for c in connectors}
    assert {"snowflake", "databricks", "fabric", "bigquery", "oracle", "collibra"} <= keys
    snowflake = next(c for c in connectors if c["key"] == "snowflake")
    assert snowflake["permission_manifest"]["reads_row_data"] is False
    assert snowflake["permission_manifest"]["grants"]
    assert snowflake["live_harvest_available"] is True


def test_check_and_rubric_catalog(client: TestClient) -> None:
    checks = client.get("/api/checks").json()["checks"]
    assert len(checks) >= 40
    rubric = client.get("/api/rubrics/2.0").json()
    assert rubric["version"] == "2.0"
    assert len(rubric["pillars"]) == 8
    assert {o["cap_scope"] for o in rubric["overrides"]} == {
        "security",
        "agent_readiness",
        "ARI",
        "RRI",
    }


def test_assessment_lifecycle(client: TestClient, demo_snapshot: str) -> None:
    detail = client.get(f"/api/assessments/{demo_snapshot}").json()
    assert detail["status"] == "complete"
    assert detail["snapshot_hash"]

    scores = client.get(f"/api/assessments/{demo_snapshot}/scores").json()["scores"]
    assert {s["scope"] for s in scores} >= {"criterion", "pillar", "composite", "index"}

    evidence = client.get(
        f"/api/assessments/{demo_snapshot}/evidence", params={"pillar": "security"}
    ).json()["evidence"]
    assert evidence and all(e["pillar_key"] == "security" for e in evidence)

    detail_evidence = client.get(f"/api/evidence/{evidence[0]['id']}").json()
    assert "failing_targets" in detail_evidence
    assert detail_evidence["rationale"]


def test_every_score_traces_to_evidence(client: TestClient, demo_snapshot: str) -> None:
    """No unexplained numbers: every criterion score names the evidence behind it."""
    architect = client.get(f"/api/assessments/{demo_snapshot}/dashboard/architect").json()
    assert architect["criteria"]
    for criterion in architect["criteria"]:
        assert criterion["evidence_ids"], f"{criterion['key']} has no evidence"
        assert criterion["evidence"], f"{criterion['key']} evidence does not resolve"


def test_executive_dashboard(client: TestClient, demo_snapshot: str) -> None:
    view = client.get(f"/api/assessments/{demo_snapshot}/dashboard/executive").json()
    assert view["assessment"]["grade"]
    assert len(view["top_risks"]) <= 5
    assert view["caps_applied"]
    assert view["roadmap"]
    assert view["advisor_narrative"] is None or view["advisor_narrative"]["body"]
    for benchmark in view["benchmarks"]:
        # A percentile is meaningless without its cohort definition.
        assert benchmark["cohort_definition"]["industry"]
        assert benchmark["cohort_definition"]["n"] > 0


def test_steward_queue_separates_review_from_findings(
    client: TestClient, demo_snapshot: str
) -> None:
    view = client.get(f"/api/assessments/{demo_snapshot}/dashboard/steward").json()
    assert all(e["status"] == "pending_review" for e in view["review_queue"])
    assert all(e["status"] == "accepted" for e in view["findings_queue"])
    assert view["workload"]["failing_targets"] > 0


def test_simulation_projects_cap_relief(client: TestClient, demo_snapshot: str) -> None:
    response = client.post(
        f"/api/assessments/{demo_snapshot}/simulate",
        json={"targets": {"SE-002": 100, "AG-006": 100, "RG-005": 100}},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["projected_composite"] > body["baseline_composite"]
    assert set(body["cleared_caps"]) == {
        "unprotected_classified_columns",
        "no_agent_action_audit",
        "no_agent_action_audit_index",
        "rag_acl_not_enforced",
    }


def test_simulation_rejects_unknown_checks(client: TestClient, demo_snapshot: str) -> None:
    response = client.post(
        f"/api/assessments/{demo_snapshot}/simulate", json={"targets": {"XX-999": 100}}
    )
    assert response.status_code == 400
    assert "XX-999" in response.json()["detail"]


def test_verify_endpoint_confirms_reproducibility(client: TestClient, demo_snapshot: str) -> None:
    body = client.get(f"/api/assessments/{demo_snapshot}/verify").json()
    assert body["reproducible"] is True
    assert body["recorded_hash"] == body["replayed_hash"]
    assert body["rubric_source_digest"]


def test_advisor_narrative_is_grounded_and_draft(client: TestClient, demo_snapshot: str) -> None:
    body = client.post(f"/api/assessments/{demo_snapshot}/advisor").json()
    assert body["status"] == "draft"
    assert body["prompt_recorded"] is True
    assert body["body"]

    evidence_ids = {
        e["id"] for e in client.get(f"/api/assessments/{demo_snapshot}/evidence").json()["evidence"]
    }
    assert set(body["citations"]) <= evidence_ids, "advisor cited evidence outside the snapshot"


def test_recommendations_are_drafts_until_approved(client: TestClient, demo_snapshot: str) -> None:
    recommendations = client.get(
        f"/api/assessments/{demo_snapshot}/recommendations"
    ).json()["recommendations"]
    assert recommendations
    assert all(r["status"] == "draft" for r in recommendations)
    assert all(r["evidence_ids"] for r in recommendations)

    approved = client.post(
        f"/api/recommendations/{recommendations[0]['id']}/review",
        json={"decision": "approved", "reviewer": "cdo@test", "note": "Do it"},
    ).json()
    assert approved["status"] == "approved"
    assert approved["reviewed_by"] == "cdo@test"


def test_sampling_authorization_is_logged_but_not_enabling(client: TestClient) -> None:
    client.post(
        "/api/tenants",
        json={"key": "sampling-test", "name": "Sampling Test", "industry": "retail"},
    )
    response = client.post(
        "/api/sampling-authorizations",
        json={
            "tenant_key": "sampling-test",
            "dataset_urn": "snowflake://ANALYTICS.SALES.ORDERS",
            "authorized_by": "dpo@test",
            "justification": "One-off validation of masking behaviour",
        },
    )
    body = response.json()
    assert response.status_code == 201
    assert body["sampling_module_installed"] is False


def test_questionnaire_round_trip(client: TestClient) -> None:
    sections = client.get("/api/questionnaire").json()["sections"]
    assert len(sections) == 3
    client.post(
        "/api/tenants", json={"key": "questionnaire-test", "name": "Questionnaire Test"}
    )
    response = client.post(
        "/api/questionnaire",
        json={
            "tenant_key": "questionnaire-test",
            "responses": [
                {
                    "question_id": "Q-GOV-02",
                    "question": sections[0]["questions"][1]["question"],
                    "answer": "About 90%",
                    "numeric_answer": 90,
                }
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["recorded"] == 1


def test_unknown_snapshot_is_404(client: TestClient) -> None:
    assert client.get("/api/assessments/snap_missing").status_code == 404
