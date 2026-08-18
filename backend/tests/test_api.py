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

def test_portfolio_groups_organisations_by_industry(client: TestClient) -> None:
    """The executive view opens on a portfolio, so it must span industries."""
    industries = client.get("/api/portfolio").json()["industries"]
    assert industries, "portfolio is empty"
    for industry in industries:
        assert industry["industry_label"], "an industry must carry a readable label"
        assert industry["organisations"]
        for org in industry["organisations"]:
            assert org["snapshot_id"] and org["grade"]
            # Scores are ordered strongest-first within an industry.
        scores = [o["composite_score"] for o in industry["organisations"]]
        assert scores == sorted(scores, reverse=True)


def test_indices_use_their_full_names(client: TestClient, demo_snapshot: str) -> None:
    """ARI/RRI are keys, not labels: a reader sees the rubric's own index names."""
    scores = client.get(f"/api/assessments/{demo_snapshot}/scores").json()["scores"]
    index_names = {s["key"]: s["name"] for s in scores if s["scope"] == "index"}
    assert index_names == {"ARI": "Agent Readiness Index", "RRI": "RAG Readiness Index"}

    view = client.get(f"/api/assessments/{demo_snapshot}/dashboard/executive").json()
    labels = {b["metric_key"]: b["label"] for b in view["benchmarks"]}
    assert labels["ARI"] == "Agent Readiness Index"
    assert labels["RRI"] == "RAG Readiness Index"
    assert labels["composite"] == "Composite readiness"
    assert labels["data_quality"] == "Data Quality"


def test_methodology_shows_its_own_arithmetic(client: TestClient, demo_snapshot: str) -> None:
    """The methodology view must reproduce every weighted mean it explains.

    It recomputes each pillar, the composite and both indices from the stored
    score lines. If any of those disagreed with the engine, the page would be
    teaching arithmetic the product does not actually perform.
    """
    view = client.get("/api/methodology", params={"snapshot": demo_snapshot}).json()
    assert view["assessment"]["snapshot_id"] == demo_snapshot

    scoring_pillars = [p for p in view["pillars"] if p["score"] is not None]
    assert len(scoring_pillars) == 8
    for pillar in scoring_pillars:
        assert pillar["reconciles"], f"{pillar['key']} does not reconcile with the engine"
        assert pillar["criteria"]
        measured = [c for c in pillar["criteria"] if c["measured"]]
        assert measured, f"{pillar['key']} has no measured criterion"
        # Every measured criterion carries the evidence that produced it.
        assert all(c["evidence"] for c in measured)

    assert view["composite"]["reconciles"]
    # The view rounds for display; it must still be the same number.
    assert view["composite"]["score"] == pytest.approx(
        view["assessment"]["composite_score"], abs=0.01
    )
    assert {i["key"] for i in view["indices"]} == {"ARI", "RRI"}
    assert all(index["reconciles"] for index in view["indices"])


def test_methodology_separates_the_kinds_of_missing(
    client: TestClient, demo_snapshot: str
) -> None:
    """A gap the connector cannot see is not a gap awaiting a reviewer."""
    view = client.get("/api/methodology", params={"snapshot": demo_snapshot}).json()
    coverage = view["coverage"]
    assert {c["status"] for c in coverage["unmeasured_criteria"]} <= {
        "missing_capability",
        "held_for_review",
        "nothing_to_measure",
    }
    for criterion in coverage["unmeasured_criteria"]:
        assert criterion["why"]
        if criterion["status"] == "missing_capability":
            assert criterion["missing_capabilities"]
        if criterion["status"] == "held_for_review":
            assert criterion["evidence_records"] > 0

    # Pending-review evidence is reported, never silently folded into a score.
    pending = {e["check_id"] for e in coverage["pending_review"]}
    held = {c["check_id"] for c in coverage["unmeasured_criteria"] if c["status"] == "held_for_review"}
    assert held <= pending
    assert coverage["never_collected"]
    assert view["settings"]["row_sampling_enabled"] is False


def test_methodology_publishes_synthetic_provenance(
    client: TestClient, demo_snapshot: str
) -> None:
    """A reader must be able to tell a synthetic estate from a real harvest."""
    view = client.get("/api/methodology", params={"snapshot": demo_snapshot}).json()
    connector = view["provenance"]["connectors"][0]
    assert connector["connector"] == "demo"
    assert connector["config"]["synthetic"] is True
    assert connector["config"]["industry"] and connector["config"]["maturity"]
    assert connector["config"]["seed"]
    assert connector["counts"]["datasets"] > 0
    # Provenance is disclosure, not a credential dump.
    assert not {"password", "token", "secret", "user", "account"} & set(connector["config"])


def test_methodology_defaults_to_an_estate_without_a_snapshot(client: TestClient, demo_snapshot: str) -> None:
    view = client.get("/api/methodology").json()
    assert view["default_snapshot"]
    assert view["requested_snapshot"] is None
    assert view["pillars"]


def test_methodology_sample_carries_every_blocker_property(
    client: TestClient, demo_snapshot: str
) -> None:
    """AG-006 and RG-005 each read several properties; showing one would mislead.

    An agent whose actions are logged still fails AG-006 under a shared identity,
    and a corpus whose ACLs propagate still fails RG-005 with no retrieval-time
    enforcement. The sample rows must carry every property the check reads so a
    blocked estate cannot be made to look clear.
    """
    sample = client.get(
        "/api/methodology", params={"snapshot": demo_snapshot}
    ).json()["provenance"]["sample"]

    assert sample["agents"]
    for agent in sample["agents"]:
        assert {"identity_kind", "action_audit", "replayable_trail"} <= set(agent)

    assert sample["rag_corpora"]
    for corpus in sample["rag_corpora"]:
        assert {"acl_propagated", "retrieval_filter_enforced", "contains_classified"} <= set(corpus)


def test_pillar_guide_covers_every_pillar_and_index(client: TestClient) -> None:
    """A new pillar cannot ship without its explanation.

    The guide is teaching material for people adopting AI, so a pillar with no
    entry would appear on the page as an unexplained weight. This test is the
    thing that stops that happening.
    """
    rubric = client.get("/api/rubrics/2.0").json()
    guide = client.get("/api/pillars").json()

    assert {p["key"] for p in guide["pillars"]} == {p["key"] for p in rubric["pillars"]}
    assert {i["key"] for i in guide["indices"]} == set(rubric["indices"])

    for pillar in guide["pillars"]:
        assert pillar["headline"], pillar["key"]
        assert pillar["why_it_matters"], pillar["key"]
        # The question the user asked this page to answer.
        assert pillar["if_unassessed"], pillar["key"]
        assert pillar["without_it"] and pillar["good_looks_like"], pillar["key"]
        assert pillar["references"], pillar["key"]

    for index in guide["indices"]:
        assert index["headline"] and index["why_it_matters"] and index["if_unassessed"]


def test_pillar_guide_takes_its_numbers_from_the_rubric(client: TestClient) -> None:
    """Explanations are data; weights and targets are not restated in prose.

    If the guide carried its own copy of a weight it would eventually disagree
    with the engine, and the page would teach arithmetic the product does not
    perform. Every number below is asserted to come from the rubric tables.
    """
    rubric = {p["key"]: p for p in client.get("/api/rubrics/2.0").json()["pillars"]}
    guide = client.get("/api/pillars").json()
    checks = {c["check_id"] for c in client.get("/api/checks").json()["checks"]}

    for pillar in guide["pillars"]:
        source = rubric[pillar["key"]]
        assert pillar["weight"] == source["weight"]
        assert pillar["core_question"] == source["core_question"]
        assert len(pillar["criteria"]) == len(source["criteria"])
        by_key = {c["key"]: c for c in source["criteria"]}
        for criterion in pillar["criteria"]:
            assert criterion["weight"] == by_key[criterion["key"]]["weight"]
            assert criterion["target"] == by_key[criterion["key"]]["target"]
            assert criterion["check_id"] in checks

    totals = guide["totals"]
    assert totals["pillars"] == len(rubric)
    assert totals["criteria"] == sum(len(p["criteria"]) for p in rubric.values())


def test_pillar_guide_references_are_citable(client: TestClient) -> None:
    """Every reference names a title and a source; any URL is https."""
    guide = client.get("/api/pillars").json()
    for pillar in guide["pillars"]:
        for reference in pillar["references"]:
            assert reference["title"].strip()
            assert reference["source"].strip()
            if reference.get("url"):
                assert reference["url"].startswith("https://"), reference["url"]


def test_pillar_guide_reports_hard_blockers_against_their_scope(client: TestClient) -> None:
    """A cap belongs to the pillar or index it caps, wherever it is displayed."""
    guide = client.get("/api/pillars").json()
    scoped = {
        **{p["key"]: p["overrides"] for p in guide["pillars"]},
        **{i["key"]: i["overrides"] for i in guide["indices"]},
    }
    assert {o["key"] for o in scoped["security"]} == {"unprotected_classified_columns"}
    assert {o["key"] for o in scoped["agent_readiness"]} == {"no_agent_action_audit"}
    assert {o["key"] for o in scoped["ARI"]} == {"no_agent_action_audit_index"}
    assert {o["key"] for o in scoped["RRI"]} == {"rag_acl_not_enforced"}
    assert scoped["data_quality"] == []


# --------------------------------------------------------------------------- #
# live demo
# --------------------------------------------------------------------------- #


def test_demo_options_are_self_consistent(client: TestClient) -> None:
    """Every default the form ships with must be a member of its own catalog."""
    options = client.get("/api/demo/options").json()
    assert options["synthetic"] is True
    catalogs = {
        "platform": {o["key"] for o in options["platforms"]},
        "governance_tool": {o["key"] for o in options["governance_tools"]},
        "dq_tool": {o["key"] for o in options["dq_tools"]},
        "maturity": {o["key"] for o in options["maturities"]},
        "industry": {o["key"] for o in options["industries"]},
        "size_band": {o["key"] for o in options["size_bands"]},
    }
    for field, keys in catalogs.items():
        assert options["defaults"][field] in keys, field
    # The platforms an audience can demo are a superset of the live connectors,
    # and the catalog says which is which rather than implying they are the same.
    assert {"snowflake", "databricks", "fabric", "bigquery", "redshift", "oracle", "teradata"} == catalogs["platform"]
    assert all(option["note"] for option in options["platforms"])


def test_demo_run_assesses_the_chosen_platform_and_tooling(client: TestClient) -> None:
    response = client.post(
        "/api/demo/run",
        json={
            "organisation": "Cobalt Union Bank",
            "industry": "financial_services",
            "platform": "teradata",
            "governance_tool": "atlan",
            "dq_tool": "soda",
            "maturity": "emerging",
            "size_band": "enterprise",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["composite_score"] is not None and body["grade"]
    assert body["configuration"]["platform"] == "teradata"

    snapshot = body["snapshot_id"]
    evidence = client.get(f"/api/assessments/{snapshot}/evidence").json()["evidence"]
    platforms = {e["platform"] for e in evidence}
    assert "teradata" in platforms, "the chosen platform must be what was actually assessed"

    # A demo snapshot is a real snapshot: it replays to the same hash.
    verify = client.get(f"/api/assessments/{snapshot}/verify").json()
    assert verify["reproducible"] is True


def test_demo_run_is_deterministic_for_the_same_configuration(client: TestClient) -> None:
    """Same choices and seed, same evidence -- so a demo can be repeated on stage."""
    payload = {
        "organisation": "Repeatable Estate",
        "industry": "retail",
        "platform": "redshift",
        "governance_tool": "alation",
        "dq_tool": "ataccama",
        "maturity": "advancing",
        "seed": 4242,
    }
    first = client.post("/api/demo/run", json=payload).json()
    second = client.post("/api/demo/run", json=payload).json()
    assert first["composite_score"] == second["composite_score"]
    assert first["stats"]["evidence_records"] == second["stats"]["evidence_records"]

    # Re-running replaces the demo tenant's snapshot rather than accumulating a
    # meaningless trend line.
    assessments = client.get("/api/assessments").json()["assessments"]
    for_tenant = [a for a in assessments if a["tenant_key"] == "demo-repeatable-estate"]
    assert len(for_tenant) == 1


def test_demo_scope_switch_reports_gaps_instead_of_scoring_zero(client: TestClient) -> None:
    """Leaving a surface out is a coverage gap, not a failing grade."""
    body = client.post(
        "/api/demo/run",
        json={"organisation": "Narrow Scope Co", "scopes_off": ["agents", "rag_corpora"]},
    ).json()
    snapshot = body["snapshot_id"]

    skipped = set(body["stats"]["checks_skipped"])
    assert {"AG-004", "AG-005", "AG-006", "AG-007", "RG-001"} <= skipped

    evidence = client.get(f"/api/assessments/{snapshot}/evidence").json()["evidence"]
    assert not [e for e in evidence if e["check_id"].startswith("RG-")]

    plan = client.get(f"/api/assessments/{snapshot}/action-plan").json()
    gaps = {a["check_id"] for a in plan["architect_actions"] if a["kind"] == "no_coverage"}
    assert {"AG-006", "RG-005"} <= gaps
    # And nothing claims those checks failed.
    below = {a["check_id"] for a in plan["architect_actions"] if a["kind"] == "below_target"}
    assert not (below & gaps)


def test_demo_rejects_a_platform_it_cannot_generate(client: TestClient) -> None:
    response = client.post(
        "/api/demo/run", json={"organisation": "Mystery Co", "platform": "mainframe"}
    )
    assert response.status_code == 400
    assert "mainframe" in response.json()["detail"]


def test_action_plan_only_names_work_the_evidence_supports(
    client: TestClient, demo_snapshot: str
) -> None:
    """Every action resolves to a check that ran, and to objects that failed."""
    plan = client.get(f"/api/assessments/{demo_snapshot}/action-plan").json()
    checks = {c["check_id"] for c in client.get("/api/checks").json()["checks"]}
    evidence = client.get(f"/api/assessments/{demo_snapshot}/evidence").json()["evidence"]
    by_check = {e["check_id"]: e for e in evidence}

    assert plan["architect_actions"]
    for action in plan["architect_actions"]:
        assert action["check_id"] in checks
        if action["kind"] == "below_target":
            assert action["score"] is not None and action["target"] is not None
            assert action["score"] < action["target"]
            assert action["check_id"] in by_check
            assert len(action["failing_sample"]) <= action["failing_total"]

    # Steward decisions are exactly the evidence held below the threshold.
    decisions = {a["evidence_id"] for a in plan["steward_actions"] if a["kind"] == "decide"}
    pending = {e["id"] for e in evidence if e["status"] == "pending_review"}
    assert decisions == pending

    # Blockers match what the engine recorded on the snapshot.
    assessment = client.get(f"/api/assessments/{demo_snapshot}").json()
    recorded = {b["override"] for b in assessment["stats"]["blockers_triggered"]}
    assert {b["override"] for b in plan["blockers"]} == recorded

    # The projection is the roadmap's measured impact, not an aspiration.
    assert plan["projection"]["projected_composite"] >= plan["projection"]["current_composite"]
    assert plan["horizons"]


def test_demo_options_offer_the_assessed_organizations_by_industry(
    client: TestClient, demo_snapshot: str
) -> None:
    """The form is industry-first, so its organizations must match the portfolio.

    A picker showing an organization the Organizations tab does not have -- or
    filing one under the wrong industry -- would make the demo disagree with the
    product's own front page.
    """
    options = client.get("/api/demo/options").json()
    portfolio = client.get("/api/portfolio").json()["industries"]

    expected = {
        (industry["industry"], org["tenant"], org["size_band"])
        for industry in portfolio
        for org in industry["organisations"]
    }
    actual = {(o["industry"], o["name"], o["size_band"]) for o in options["organisations"]}
    assert actual == expected

    industry_keys = {i["key"] for i in options["industries"]}
    assert {o["industry"] for o in options["organisations"]} <= industry_keys


def test_demo_run_for_an_existing_organization_leaves_it_untouched(
    client: TestClient, demo_snapshot: str
) -> None:
    """Running the demo as a portfolio organization must not overwrite it."""
    client.post(
        "/api/tenants",
        json={
            "key": "reference-estate",
            "name": "Reference Estate",
            "industry": "utilities",
            "size_band": "enterprise",
        },
    )
    client.post("/api/assessments", json={"tenant_key": "reference-estate", "label": "baseline"})
    before = client.get("/api/assessments").json()["assessments"]
    reference = next(a for a in before if a["tenant_key"] == "reference-estate")

    demo = client.post(
        "/api/demo/run",
        json={"organisation": "Reference Estate", "industry": "utilities", "maturity": "leading"},
    ).json()

    assert demo["tenant_key"] == "demo-reference-estate"
    # Named apart, so two rows in the portfolio cannot be confused.
    assert demo["tenant"] == "Reference Estate (demo run)"

    after = client.get("/api/assessments").json()["assessments"]
    still_there = next(a for a in after if a["tenant_key"] == "reference-estate")
    assert still_there["snapshot_id"] == reference["snapshot_id"]
    assert still_there["composite_score"] == reference["composite_score"]


def test_integration_guide_documents_every_registered_connector(client: TestClient) -> None:
    """The API Documentation view must cover the registry, not a snapshot of it.

    A connector added to the registry without a guide entry would otherwise
    appear on the page with empty auth and configuration sections -- which reads
    as "needs nothing" rather than "nobody wrote this down yet".
    """
    from eairn.connectors.registry import REGISTRY

    guide = client.get("/api/integration").json()
    documented = {c["key"] for c in guide["connectors"]}
    assert documented == set(REGISTRY)
    assert all(c["documented"] for c in guide["connectors"]), [
        c["key"] for c in guide["connectors"] if not c["documented"]
    ]

    for connector in guide["connectors"]:
        assert connector["summary"], connector["key"]
        assert connector["auth"], connector["key"]
        assert connector["permission_manifest"]["reads_row_data"] is False, connector["key"]

    # Live drivers sort ahead of bundle-backed ones.
    live = [i for i, c in enumerate(guide["connectors"]) if c["live_harvest_available"]]
    bundled = [i for i, c in enumerate(guide["connectors"]) if not c["live_harvest_available"]]
    assert max(live) < min(bundled)


def test_integration_guide_publishes_verified_read_only_calls(client: TestClient) -> None:
    """Every catalogued call is re-validated as the page renders, and none fails."""
    guide = client.get("/api/integration").json()

    assert guide["totals"]["read_only_violations"] == 0
    calls = [call for c in guide["connectors"] for call in c["calls"]]
    assert calls
    assert all(call["read_only_verified"] for call in calls)
    assert all(call["statement"] for call in calls)
    assert guide["totals"]["documented_calls"] == len(calls)

    # A POST only appears when it has been reviewed as a read-only search endpoint.
    posts = [call for call in calls if call.get("method") == "POST"]
    assert posts and all(call["reviewed_read_only_post"] for call in posts)

    snowflake = next(c for c in guide["connectors"] if c["key"] == "snowflake")
    tables = next(call for call in snowflake["calls"] if call["name"] == "tables")
    assert "SNOWFLAKE.ACCOUNT_USAGE.TABLES" in tables["statement"]
    assert tables["kind"] == "sql"


def test_integration_guide_maps_capabilities_to_checks(client: TestClient) -> None:
    """Coverage is stated in checks, and the two directions have to agree."""
    guide = client.get("/api/integration").json()
    total_checks = guide["totals"]["registered_checks"]

    for connector in guide["connectors"]:
        coverage = connector["coverage"]
        assert coverage["unlocked_count"] + coverage["blocked_count"] == total_checks
        unlocked = {
            check["check_id"] for pillar in coverage["by_pillar"] for check in pillar["checks"]
        }
        assert len(unlocked) == coverage["unlocked_count"]

    # RAG checks need a corpus, and no platform connector supplies one -- which is
    # exactly why RG-005 reports as not measured on a Snowflake-only assessment.
    matrix = {row["capability"]: row for row in guide["capability_matrix"]}
    assert "RG-005" in {check["check_id"] for check in matrix["rag_corpora"]["checks"]}
    snowflake = next(c for c in guide["connectors"] if c["key"] == "snowflake")
    blocked = {check["check_id"] for check in snowflake["coverage"]["still_unmeasured"]}
    assert "RG-005" in blocked

    # Pillar names come from the installed rubric, not from a hardcoded label map.
    assert "Agent Readiness" in {
        pillar["pillar_name"]
        for connector in guide["connectors"]
        for pillar in connector["coverage"]["by_pillar"]
    }


def test_integration_guide_never_leaks_a_credential(client: TestClient) -> None:
    """Secret configuration keys are named, never given a value."""
    guide = client.get("/api/integration").json()
    secrets = [
        field
        for connector in guide["connectors"]
        for field in connector["config_fields"]
        if field["secret"]
    ]
    assert secrets

    def is_placeholder(example: str) -> bool:
        # Either masked, or an absolute path naming where the credential is
        # mounted. A path is not itself a credential and is worth showing.
        return "***" in example or example.startswith("/")

    offenders = [field["key"] for field in secrets if not is_placeholder(field["example"])]
    assert not offenders, offenders

    # The live database URL is echoed back for orientation, with any password removed.
    variables = {v["name"]: v for v in guide["hosting"]["environment"]["variables"]}
    assert variables["EAIRN_ANTHROPIC_API_KEY"]["current"] in {"set", "unset"}
    assert "@" not in variables["EAIRN_DATABASE_URL"]["current"].split("://", 1)[-1].split("/")[0]


def test_data_model_reflects_the_orm(client: TestClient) -> None:
    """Every mapped table appears exactly once, in exactly one family."""
    from eairn.models import Base

    model = client.get("/api/data-model").json()
    listed = [table["name"] for family in model["families"] for table in family["tables"]]
    assert sorted(listed) == sorted(Base.metadata.tables)
    assert len(listed) == len(set(listed)), "a table is listed in more than one family"
    assert model["totals"]["tables"] == len(listed)
    assert {f["key"] for f in model["families"]} == {
        "tenancy",
        "canonical",
        "rubric",
        "assessment",
    }, "an unclassified family means a table was added without a family entry"

    evidence = next(
        table
        for family in model["families"]
        for table in family["tables"]
        if table["name"] == "evidence"
    )
    assert evidence["class_name"] == "Evidence"
    assert evidence["purpose"]
    assert evidence["primary_key"] == ["id"]
    assert {c["name"] for c in evidence["columns"]} >= {"check_id", "result", "confidence"}


def test_data_model_renders_postgres_ddl(client: TestClient) -> None:
    """The DDL is Postgres, not the SQLite this instance happens to run on."""
    model = client.get("/api/data-model").json()
    corpora = next(
        table
        for family in model["families"]
        for table in family["tables"]
        if table["name"] == "rag_corpora"
    )

    assert corpora["postgres_ddl"].startswith("CREATE TABLE rag_corpora")
    assert "SERIAL" in corpora["postgres_ddl"], "an autoincrement key should render as SERIAL"
    # The per-column type is produced by the same compiler as the DDL, so the two
    # cannot disagree about an identity column.
    assert next(c for c in corpora["columns"] if c["name"] == "id")["postgres_type"] == "SERIAL"
    assert corpora["populated_by_capability"] == "rag_corpora"

    # Tenant-keyed tables cascade, which is what makes deleting an organisation
    # a single statement rather than a cleanup script.
    cascades = {
        (edge["from_table"], edge["to_table"])
        for edge in model["relationships"]
        if edge["on_delete"] == "CASCADE"
    }
    assert ("rag_corpora", "tenants") in cascades
    assert ("evidence", "assessments") in cascades


def test_data_model_counts_rows_and_flags_the_dialect(client: TestClient, demo_snapshot: str) -> None:
    """Row counts come from the live database, and SQLite is flagged as non-production."""
    model = client.get("/api/data-model").json()
    evidence = next(
        table
        for family in model["families"]
        for table in family["tables"]
        if table["name"] == "evidence"
    )

    assert evidence["row_count"] and evidence["row_count"] > 0
    assert model["totals"]["rows"] >= evidence["row_count"]
    assert model["deployment"]["current_dialect"] == "sqlite"
    assert model["deployment"]["is_production_target"] is False
    assert any(target["platform"] == "AWS" for target in model["deployment"]["targets"])
