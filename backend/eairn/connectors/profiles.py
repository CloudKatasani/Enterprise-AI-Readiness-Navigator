"""Industry and maturity profiles for the demo connector.

The sample estates exist so the Portal can be evaluated against more than one
shape of organisation. Two axes vary independently:

* **Industry** decides the business domains, the dominant platform and where
  sensitive data concentrates -- a utility's crown jewels sit in metering and
  outage data, a telco's in subscriber and roaming records.
* **Maturity** decides the coverage rates a governance programme has actually
  achieved. It is a set of dials, not a target score: each profile produces its
  own evidence and the scoring engine reaches whatever grade that evidence
  supports.

Nothing here is a scoring shortcut. A profile cannot set a grade, only the
estate facts the checks then measure.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaturityProfile:
    """Coverage dials for a governance programme at a given stage."""

    key: str
    label: str
    tier1_description_rate: float
    tier2_description_rate: float
    table_description_rate: float
    owner_rate: float
    owner_verified_rate: float
    certification_rate: float
    curation_rate: float
    glossary_rate: float
    tier1_protection_rate: float
    other_protection_rate: float
    classification_rate: float
    lineage_rate: float
    column_lineage_rate: float
    monitor_validity_rate: float
    tier2_monitor_rate: float
    rules_as_data_rate: float
    monitor_pass_floor: float
    incident_detected_rate: float
    incident_resolved_rate: float
    incident_owned_rate: float
    incident_false_positive_rate: float
    model_registered_rate: float
    model_lineage_rate: float
    promotion_gate_rate: float
    gateway_rate: float
    certifications_completed_ratio: float
    steward_response_hours: float
    glossary_linked_ratio: float
    access_reviews_current: bool
    #: Agent posture: (distinct identity, scoped roles, approval gate, audit,
    #: replayable trail, entitlement reconciliation, inference control).
    agent_posture: tuple[bool, bool, bool, bool, bool, bool, bool]
    #: RAG posture on the primary corpus: (ACLs propagate, filter enforced,
    #: eval set, citation enforcement, hallucination monitoring).
    rag_posture: tuple[bool, bool, bool, bool, bool]
    rag_index_coverage: float
    rag_metadata_rate: float
    rag_refresh_hours: float


MATURITY_PROFILES: dict[str, MaturityProfile] = {
    "leading": MaturityProfile(
        key="leading",
        label="Governance programme complete on Tier-1, agent controls in production",
        tier1_description_rate=0.94,
        tier2_description_rate=0.78,
        table_description_rate=0.92,
        owner_rate=0.97,
        owner_verified_rate=0.93,
        certification_rate=0.88,
        curation_rate=0.9,
        glossary_rate=0.85,
        tier1_protection_rate=1.0,
        other_protection_rate=0.96,
        classification_rate=0.97,
        lineage_rate=0.97,
        column_lineage_rate=0.9,
        monitor_validity_rate=0.95,
        tier2_monitor_rate=0.85,
        rules_as_data_rate=0.95,
        monitor_pass_floor=0.95,
        incident_detected_rate=0.93,
        incident_resolved_rate=0.97,
        incident_owned_rate=0.96,
        incident_false_positive_rate=0.05,
        model_registered_rate=1.0,
        model_lineage_rate=0.95,
        promotion_gate_rate=1.0,
        gateway_rate=1.0,
        certifications_completed_ratio=0.93,
        steward_response_hours=18.0,
        glossary_linked_ratio=0.88,
        access_reviews_current=True,
        agent_posture=(True, True, True, True, True, True, True),
        rag_posture=(True, True, True, True, True),
        rag_index_coverage=0.97,
        rag_metadata_rate=0.95,
        rag_refresh_hours=12.0,
    ),
    "advancing": MaturityProfile(
        key="advancing",
        label="Tier-1 governed, agent and RAG controls partially rolled out",
        tier1_description_rate=0.82,
        tier2_description_rate=0.55,
        table_description_rate=0.78,
        owner_rate=0.9,
        owner_verified_rate=0.78,
        certification_rate=0.7,
        curation_rate=0.76,
        glossary_rate=0.66,
        tier1_protection_rate=0.98,
        other_protection_rate=0.72,
        classification_rate=0.92,
        lineage_rate=0.92,
        column_lineage_rate=0.72,
        monitor_validity_rate=0.8,
        tier2_monitor_rate=0.65,
        rules_as_data_rate=0.85,
        monitor_pass_floor=0.9,
        incident_detected_rate=0.8,
        incident_resolved_rate=0.9,
        incident_owned_rate=0.85,
        incident_false_positive_rate=0.1,
        model_registered_rate=0.92,
        model_lineage_rate=0.78,
        promotion_gate_rate=0.85,
        gateway_rate=0.8,
        certifications_completed_ratio=0.8,
        steward_response_hours=40.0,
        glossary_linked_ratio=0.66,
        access_reviews_current=True,
        agent_posture=(True, True, True, True, True, False, True),
        rag_posture=(True, True, True, True, False),
        rag_index_coverage=0.88,
        rag_metadata_rate=0.8,
        rag_refresh_hours=36.0,
    ),
    "emerging": MaturityProfile(
        key="emerging",
        label="Governance programme underway; protection and agent controls unfinished",
        tier1_description_rate=0.68,
        tier2_description_rate=0.34,
        table_description_rate=0.6,
        owner_rate=0.78,
        owner_verified_rate=0.62,
        certification_rate=0.55,
        curation_rate=0.62,
        glossary_rate=0.5,
        tier1_protection_rate=0.86,
        other_protection_rate=0.34,
        classification_rate=0.82,
        lineage_rate=0.88,
        column_lineage_rate=0.62,
        monitor_validity_rate=0.55,
        tier2_monitor_rate=0.5,
        rules_as_data_rate=0.72,
        monitor_pass_floor=0.82,
        incident_detected_rate=0.62,
        incident_resolved_rate=0.78,
        incident_owned_rate=0.7,
        incident_false_positive_rate=0.18,
        model_registered_rate=0.8,
        model_lineage_rate=0.55,
        promotion_gate_rate=0.5,
        gateway_rate=0.4,
        certifications_completed_ratio=0.54,
        steward_response_hours=96.0,
        glossary_linked_ratio=0.45,
        access_reviews_current=True,
        agent_posture=(False, False, False, True, False, False, False),
        rag_posture=(False, False, True, True, False),
        rag_index_coverage=0.74,
        rag_metadata_rate=0.55,
        rag_refresh_hours=168.0,
    ),
    "at_risk": MaturityProfile(
        key="at_risk",
        label="Metadata sparse, sensitive data largely unprotected, no agent controls",
        tier1_description_rate=0.4,
        tier2_description_rate=0.18,
        table_description_rate=0.32,
        owner_rate=0.5,
        owner_verified_rate=0.3,
        certification_rate=0.25,
        curation_rate=0.32,
        glossary_rate=0.22,
        tier1_protection_rate=0.45,
        other_protection_rate=0.12,
        classification_rate=0.6,
        lineage_rate=0.6,
        column_lineage_rate=0.3,
        monitor_validity_rate=0.25,
        tier2_monitor_rate=0.2,
        rules_as_data_rate=0.4,
        monitor_pass_floor=0.7,
        incident_detected_rate=0.35,
        incident_resolved_rate=0.55,
        incident_owned_rate=0.45,
        incident_false_positive_rate=0.3,
        model_registered_rate=0.5,
        model_lineage_rate=0.25,
        promotion_gate_rate=0.2,
        gateway_rate=0.1,
        certifications_completed_ratio=0.28,
        steward_response_hours=180.0,
        glossary_linked_ratio=0.2,
        access_reviews_current=False,
        agent_posture=(False, False, False, False, False, False, False),
        rag_posture=(False, False, False, False, False),
        rag_index_coverage=0.55,
        rag_metadata_rate=0.3,
        rag_refresh_hours=336.0,
    ),
}


@dataclass(frozen=True)
class IndustryProfile:
    """Where an industry's data — and its sensitive data — actually lives."""

    key: str
    label: str
    #: (schema, business domain, base tier)
    domains: tuple[tuple[str, str, int], ...]
    #: Domains where regulated or personal data concentrates.
    sensitive_domains: frozenset[str]
    table_stems: tuple[str, ...]
    corpus_names: tuple[tuple[str, str], ...]
    agent_names: tuple[str, ...]
    model_names: tuple[str, ...]
    kpi_names: tuple[str, ...]


INDUSTRY_PROFILES: dict[str, IndustryProfile] = {
    "financial_services": IndustryProfile(
        key="financial_services",
        label="Financial Services",
        domains=(
            ("SALES", "sales", 1),
            ("FINANCE", "finance", 1),
            ("RISK", "risk", 1),
            ("CUSTOMER", "customer", 1),
            ("MARKETING", "marketing", 2),
            ("OPERATIONS", "operations", 2),
            ("HR", "hr", 2),
            ("SANDBOX", "sandbox", 3),
            ("STAGING", "staging", 3),
        ),
        sensitive_domains=frozenset({"customer", "finance", "hr", "risk"}),
        table_stems=(
            "ACCOUNTS", "TRANSACTIONS", "BALANCES", "POSITIONS", "EXPOSURES", "LIMITS",
            "COLLATERAL", "SETTLEMENTS", "CUSTOMERS", "PAYMENTS", "RISK_SCORES", "INVOICES",
        ),
        corpus_names=(("policies-and-procedures", "sharepoint"), ("product-disclosures", "confluence")),
        agent_names=("finance-analyst-copilot", "ops-remediation-agent", "customer-support-assistant"),
        model_names=("churn_propensity", "fraud_score", "credit_limit", "next_best_action", "ltv_forecast"),
        kpi_names=("Net Revenue", "Active Customer", "Exposure at Default", "Order Value", "Churn Risk"),
    ),
    "telecommunications": IndustryProfile(
        key="telecommunications",
        label="Telecommunications",
        domains=(
            ("SUBSCRIBER", "subscriber", 1),
            ("NETWORK", "network", 1),
            ("BILLING", "billing", 1),
            ("ROAMING", "roaming", 1),
            ("FIELD_OPS", "field_ops", 2),
            ("MARKETING", "marketing", 2),
            ("HR", "hr", 2),
            ("SANDBOX", "sandbox", 3),
            ("STAGING", "staging", 3),
        ),
        sensitive_domains=frozenset({"subscriber", "billing", "roaming", "hr"}),
        table_stems=(
            "SUBSCRIBERS", "CDR_EVENTS", "CELL_SITES", "NETWORK_KPIS", "PLANS", "INVOICES",
            "ROAMING_SESSIONS", "DEVICE_INVENTORY", "TICKETS", "CHURN_SIGNALS", "USAGE_DAILY", "OUTAGES",
        ),
        corpus_names=(("network-runbooks", "confluence"), ("retail-store-playbooks", "sharepoint")),
        agent_names=("network-triage-agent", "care-copilot", "field-dispatch-agent"),
        model_names=("churn_propensity", "cell_congestion", "arpu_forecast", "device_upgrade", "fraud_roaming"),
        kpi_names=("ARPU", "Active Subscriber", "Churn Rate", "Network Availability", "Cost per Gigabyte"),
    ),
    "retail": IndustryProfile(
        key="retail",
        label="Retail & Consumer",
        domains=(
            ("MERCHANDISING", "merchandising", 1),
            ("ECOMMERCE", "ecommerce", 1),
            ("SUPPLY_CHAIN", "supply_chain", 1),
            ("CUSTOMER", "customer", 1),
            ("STORES", "stores", 2),
            ("MARKETING", "marketing", 2),
            ("HR", "hr", 2),
            ("SANDBOX", "sandbox", 3),
            ("STAGING", "staging", 3),
        ),
        sensitive_domains=frozenset({"customer", "ecommerce", "hr"}),
        table_stems=(
            "ORDERS", "ORDER_LINES", "PRODUCTS", "INVENTORY", "SHIPMENTS", "STORES",
            "LOYALTY_MEMBERS", "PRICING", "PROMOTIONS", "RETURNS", "BASKETS", "SUPPLIERS",
        ),
        corpus_names=(("merchandising-guidelines", "sharepoint"), ("store-operations-manuals", "confluence")),
        agent_names=("merch-planning-copilot", "supply-exception-agent", "customer-service-assistant"),
        model_names=("demand_forecast", "basket_affinity", "markdown_optimiser", "fraud_returns", "ltv_forecast"),
        kpi_names=("Net Sales", "Active Customer", "Gross Margin", "Sell-Through Rate", "Basket Size"),
    ),
    "utilities": IndustryProfile(
        key="utilities",
        label="Utilities & Energy",
        domains=(
            ("GRID", "grid", 1),
            ("METERING", "metering", 1),
            ("OUTAGE", "outage", 1),
            ("CUSTOMER", "customer", 1),
            ("FIELD_OPS", "field_ops", 2),
            ("TRADING", "trading", 2),
            ("HR", "hr", 2),
            ("SANDBOX", "sandbox", 3),
            ("STAGING", "staging", 3),
        ),
        sensitive_domains=frozenset({"customer", "metering", "hr"}),
        table_stems=(
            "METER_READS", "SUBSTATIONS", "FEEDERS", "OUTAGE_EVENTS", "WORK_ORDERS", "ASSETS",
            "CONSUMPTION_DAILY", "TARIFFS", "CUSTOMERS", "SENSOR_TELEMETRY", "LOAD_FORECASTS", "CREWS",
        ),
        corpus_names=(("safety-and-compliance", "sharepoint"), ("asset-maintenance-manuals", "confluence")),
        agent_names=("outage-triage-agent", "asset-planning-copilot", "customer-billing-assistant"),
        model_names=("load_forecast", "asset_failure", "outage_duration", "theft_detection", "tariff_optimiser"),
        kpi_names=("Peak Demand", "SAIDI", "Active Connection", "Energy Delivered", "Cost to Serve"),
    ),
    "technology": IndustryProfile(
        key="technology",
        label="Technology & Software",
        domains=(
            ("PRODUCT", "product", 1),
            ("TELEMETRY", "telemetry", 1),
            ("BILLING", "billing", 1),
            ("CUSTOMER", "customer", 1),
            ("GROWTH", "growth", 2),
            ("SUPPORT", "support", 2),
            ("HR", "hr", 2),
            ("SANDBOX", "sandbox", 3),
            ("STAGING", "staging", 3),
        ),
        sensitive_domains=frozenset({"customer", "billing", "hr"}),
        table_stems=(
            "ACCOUNTS", "WORKSPACES", "EVENTS_DAILY", "FEATURE_USAGE", "SUBSCRIPTIONS", "INVOICES",
            "TRIALS", "SUPPORT_TICKETS", "RELEASES", "EXPERIMENTS", "SEATS", "USAGE_METERS",
        ),
        corpus_names=(("engineering-handbook", "confluence"), ("customer-facing-docs", "sharepoint")),
        agent_names=("release-triage-agent", "growth-analytics-copilot", "support-deflection-assistant"),
        model_names=("expansion_propensity", "churn_propensity", "anomaly_usage", "lead_scoring", "ticket_router"),
        kpi_names=("Annual Recurring Revenue", "Active Workspace", "Net Revenue Retention", "Activation Rate", "Support Deflection"),
    ),
    "healthcare": IndustryProfile(
        key="healthcare",
        label="Healthcare & Life Sciences",
        domains=(
            ("PATIENT", "patient", 1),
            ("CLINICAL", "clinical", 1),
            ("CLAIMS", "claims", 1),
            ("PHARMACY", "pharmacy", 1),
            ("SCHEDULING", "scheduling", 2),
            ("SUPPLY", "supply", 2),
            ("HR", "hr", 2),
            ("SANDBOX", "sandbox", 3),
            ("STAGING", "staging", 3),
        ),
        sensitive_domains=frozenset({"patient", "clinical", "claims", "pharmacy", "hr"}),
        table_stems=(
            "ENCOUNTERS", "PATIENTS", "DIAGNOSES", "PROCEDURES", "CLAIMS", "PRESCRIPTIONS",
            "LAB_RESULTS", "APPOINTMENTS", "PROVIDERS", "FORMULARY", "ADMISSIONS", "SUPPLIES",
        ),
        corpus_names=(("clinical-protocols", "sharepoint"), ("payer-policy-library", "confluence")),
        agent_names=("care-coordination-agent", "revenue-cycle-copilot", "scheduling-assistant"),
        model_names=("readmission_risk", "no_show_predictor", "claim_denial", "sepsis_early_warning", "capacity_forecast"),
        kpi_names=("Readmission Rate", "Active Patient", "Denial Rate", "Average Length of Stay", "Cost per Encounter"),
    ),
}

PLATFORM_BY_INDUSTRY: dict[str, str] = {
    "financial_services": "snowflake",
    "telecommunications": "databricks",
    "retail": "snowflake",
    "utilities": "oracle",
    "technology": "bigquery",
    "healthcare": "fabric",
}
