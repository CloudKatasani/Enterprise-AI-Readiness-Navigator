"""Canonical-bundle import.

Every connector can be fed a JSON file in the canonical metadata shape instead
of live credentials. That serves three purposes: offline demos, regression
fixtures, and partner-delivered assessments where the customer exports metadata
themselves rather than provisioning a service principal.

The file is metadata only. Any key that is not part of the canonical model is
ignored, and there is no path here that can carry row data into EAIRN.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from eairn.connectors.base import HarvestBundle
from eairn.models import (
    AgentAsset,
    Column,
    Dataset,
    DQIncident,
    DQMonitor,
    GovernanceProgram,
    Grant,
    KPIDefinition,
    LineageEdge,
    MLAsset,
    Policy,
    RAGCorpus,
    SemanticModel,
    UsageEvent,
)

_DATETIME_FIELDS = {
    "owner_verified_at", "last_queried_at", "event_date", "last_run_at", "opened_at",
    "detected_at", "consumer_reported_at", "resolved_at", "last_scan_at",
}

_ENTITY_MAP = {
    "lineage": (LineageEdge, "lineage"),
    "policies": (Policy, "policies"),
    "grants": (Grant, "grants"),
    "usage": (UsageEvent, "usage"),
    "dq_monitors": (DQMonitor, "dq_monitors"),
    "dq_incidents": (DQIncident, "dq_incidents"),
    "ml_assets": (MLAsset, "ml_assets"),
    "semantic_models": (SemanticModel, "semantic_models"),
    "kpi_definitions": (KPIDefinition, "kpi_definitions"),
    "agents": (AgentAsset, "agents"),
    "rag_corpora": (RAGCorpus, "rag_corpora"),
    "governance_programs": (GovernanceProgram, "governance_programs"),
}


def _coerce(payload: dict[str, Any], model_cls) -> dict[str, Any]:
    valid = {c.key for c in model_cls.__table__.columns}
    coerced: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in valid or key in {"id", "tenant_id", "harvest_run_id"}:
            continue
        if key in _DATETIME_FIELDS and isinstance(value, str):
            value = _parse_datetime(value)
        coerced[key] = value
    return coerced


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_canonical_bundle(path: str | Path, *, connector_key: str, platform: str) -> HarvestBundle:
    """Build a :class:`HarvestBundle` from a canonical JSON export."""
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    bundle = HarvestBundle(connector_key=connector_key, platform=platform)
    bundle.warnings = [f"harvested from canonical bundle {file_path.name}"]

    for dataset_payload in payload.get("datasets", []):
        columns = dataset_payload.pop("columns", [])
        dataset = Dataset(**_coerce(dataset_payload, Dataset))
        dataset.platform = dataset.platform or platform
        dataset.columns = [Column(**_coerce(c, Column)) for c in columns]
        bundle.datasets.append(dataset)

    for key, (model_cls, attribute) in _ENTITY_MAP.items():
        rows = payload.get(key, [])
        getattr(bundle, attribute).extend(model_cls(**_coerce(row, model_cls)) for row in rows)

    declared = payload.get("capabilities")
    bundle.capabilities = set(declared) if declared else _infer_capabilities(bundle)
    return bundle


def _infer_capabilities(bundle: HarvestBundle) -> set[str]:
    capabilities: set[str] = set()
    if bundle.datasets:
        capabilities |= {"datasets"}
        if any(d.columns for d in bundle.datasets):
            capabilities |= {"columns", "descriptions"}
        if any(c.platform_classification or c.catalog_classification for d in bundle.datasets for c in d.columns):
            capabilities.add("classification")
    for attribute, capability in (
        ("lineage", "lineage"),
        ("policies", "policies"),
        ("grants", "grants"),
        ("usage", "usage"),
        ("dq_monitors", "dq_monitors"),
        ("dq_incidents", "dq_incidents"),
        ("ml_assets", "ml_assets"),
        ("semantic_models", "semantic_models"),
        ("kpi_definitions", "kpi_definitions"),
        ("agents", "agents"),
        ("rag_corpora", "rag_corpora"),
        ("governance_programs", "governance_program"),
    ):
        if getattr(bundle, attribute):
            capabilities.add(capability)
    if any(e.level == "column" for e in bundle.lineage):
        capabilities.add("column_lineage")
    if any(g.audit_logging_enabled for g in bundle.governance_programs):
        capabilities.add("audit_config")
    return capabilities
