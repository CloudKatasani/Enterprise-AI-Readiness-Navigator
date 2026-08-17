"""Connector framework.

Every connector is a *read-only* adapter that normalises one platform or tool
into the canonical metadata model. Three contracts are mandatory:

* ``capabilities()`` -- which canonical entities this connector can populate, so
  the check library knows which checks are in scope (a check with no supporting
  evidence is reported as ``not_applicable``, never silently scored as zero).
* ``permission_manifest()`` -- the exact least-privilege grants the customer must
  provision, published to them verbatim before any connection is made.
* ``harvest()`` -- returns a :class:`HarvestBundle` of canonical entities.

Read-only is enforced mechanically, not by convention: every statement a
connector issues goes through :func:`assert_read_only`, and CI runs a kill test
that asserts each connector's query catalog is non-mutating and that the guard
rejects mutations.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from eairn.models import (
    AgentAsset,
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


class ReadOnlyViolation(RuntimeError):
    """Raised when a connector attempts anything that could mutate a customer platform."""


# Verbs that can change customer state. These are matched as whole tokens after
# string literals and quoted identifiers are stripped, so ordinary metadata
# columns (DELETED, LAST_UPDATED, CREATED_ON, EXECUTION_TIME) do not trip the
# guard while `WITH x AS (DELETE ... RETURNING ...)` still does.
_MUTATING_KEYWORDS = (
    "insert", "update", "delete", "merge", "upsert", "truncate", "drop", "create",
    "alter", "grant", "revoke", "unload", "undrop", "rename", "vacuum", "optimize",
    "call", "execute", "exec",
)
_ALLOWED_LEADING = ("select", "with", "show", "describe", "desc", "explain")
_COMMENT_RE = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)


def assert_read_only(statement: str, *, source: str = "connector") -> str:
    """Validate that `statement` is a read-only query. Returns it unchanged.

    Rejects: mutating leading keywords, stacked statements, and mutating verbs
    appearing anywhere outside of string literals or identifiers.
    """
    stripped = _COMMENT_RE.sub(" ", statement).strip().rstrip(";").strip()
    if not stripped:
        raise ReadOnlyViolation(f"{source}: empty statement")
    if ";" in stripped:
        raise ReadOnlyViolation(f"{source}: stacked statements are not permitted")

    lowered = stripped.lower()
    leading = lowered.split(None, 1)[0]
    if leading not in _ALLOWED_LEADING:
        raise ReadOnlyViolation(f"{source}: statement must start with SELECT/WITH/SHOW/DESCRIBE, got {leading!r}")

    # Strip quoted literals and identifiers before scanning for verbs, so a
    # column named CREATED_ON or a literal 'deleted' does not trip the guard.
    scrubbed = re.sub(r"'[^']*'", " ", lowered)
    scrubbed = re.sub(r'"[^"]*"', " ", scrubbed)
    scrubbed = re.sub(r"[^a-z_]+", " ", scrubbed)
    tokens = {t for t in scrubbed.split() if t}
    offenders = sorted(tokens & set(_MUTATING_KEYWORDS) - set(_ALLOWED_LEADING))
    if offenders:
        raise ReadOnlyViolation(f"{source}: mutating keyword(s) {offenders} in statement")
    return statement


#: HTTP methods a connector may issue. POST appears because several metadata
#: APIs expose *search* over POST (BigQuery lineage searchLinks, Atlas search);
#: such endpoints must be listed in ``read_only_post_endpoints`` to be accepted.
_READ_ONLY_METHODS = ("GET", "HEAD")


def assert_read_only_api(call: str, *, source: str = "connector", allowed_post: Iterable[str] = ()) -> str:
    """Validate that an API catalog entry cannot mutate customer state."""
    parts = call.strip().split(None, 1)
    if len(parts) != 2:
        raise ReadOnlyViolation(f"{source}: API entry must be '<METHOD> <url>', got {call!r}")
    method, url = parts[0].upper(), parts[1].strip()
    if method in _READ_ONLY_METHODS:
        return call
    if method == "POST" and url in set(allowed_post):
        return call
    raise ReadOnlyViolation(
        f"{source}: {method} is not a read-only method"
        + (" (POST endpoints must be declared read-only explicitly)" if method == "POST" else "")
    )


@dataclass(frozen=True)
class PermissionGrant:
    scope: str
    grant: str
    purpose: str


@dataclass(frozen=True)
class PermissionManifest:
    """Published verbatim to the customer before a connection is provisioned."""

    connector_key: str
    principal: str
    grants: tuple[PermissionGrant, ...]
    reads_row_data: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_key": self.connector_key,
            "principal": self.principal,
            "reads_row_data": self.reads_row_data,
            "notes": self.notes,
            "grants": [g.__dict__ for g in self.grants],
        }


@dataclass
class HarvestBundle:
    """Canonical entities produced by one connector run.

    Entities are unsaved ORM instances; the pipeline stamps tenant/run ids and
    persists them. ``capabilities`` records which entity families this run could
    actually observe.
    """

    connector_key: str
    platform: str
    datasets: list[Dataset] = field(default_factory=list)
    lineage: list[LineageEdge] = field(default_factory=list)
    policies: list[Policy] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)
    usage: list[UsageEvent] = field(default_factory=list)
    dq_monitors: list[DQMonitor] = field(default_factory=list)
    dq_incidents: list[DQIncident] = field(default_factory=list)
    ml_assets: list[MLAsset] = field(default_factory=list)
    semantic_models: list[SemanticModel] = field(default_factory=list)
    kpi_definitions: list[KPIDefinition] = field(default_factory=list)
    agents: list[AgentAsset] = field(default_factory=list)
    rag_corpora: list[RAGCorpus] = field(default_factory=list)
    governance_programs: list[GovernanceProgram] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    def stats(self) -> dict[str, int]:
        return {
            "datasets": len(self.datasets),
            "columns": sum(len(d.columns) for d in self.datasets),
            "lineage_edges": len(self.lineage),
            "policies": len(self.policies),
            "grants": len(self.grants),
            "usage_events": len(self.usage),
            "dq_monitors": len(self.dq_monitors),
            "dq_incidents": len(self.dq_incidents),
            "ml_assets": len(self.ml_assets),
            "semantic_models": len(self.semantic_models),
            "kpi_definitions": len(self.kpi_definitions),
            "agents": len(self.agents),
            "rag_corpora": len(self.rag_corpora),
            "governance_programs": len(self.governance_programs),
        }


# Capability keys a connector may declare. Checks declare which they require.
CAPABILITIES = {
    "datasets",
    "columns",
    "descriptions",
    "classification",
    "policies",
    "lineage",
    "column_lineage",
    "grants",
    "usage",
    "dq_monitors",
    "dq_incidents",
    "ml_assets",
    "semantic_models",
    "kpi_definitions",
    "agents",
    "rag_corpora",
    "governance_program",
    "audit_config",
}


class Connector(ABC):
    """Base class for all EAIRN connectors."""

    key: ClassVar[str] = "base"
    platform: ClassVar[str] = "unknown"
    display_name: ClassVar[str] = "Base connector"
    #: SQL statements this connector may issue, keyed by query name. Published
    #: for customer review and asserted read-only by the CI kill test.
    query_catalog: ClassVar[dict[str, str]] = {}
    #: HTTP calls this connector may issue, as "<METHOD> <url template>".
    api_catalog: ClassVar[dict[str, str]] = {}
    #: Search-style POST endpoints explicitly reviewed as read-only.
    read_only_post_endpoints: ClassVar[tuple[str, ...]] = ()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    # -- contracts ---------------------------------------------------------- #

    @abstractmethod
    def capabilities(self) -> set[str]:
        """Canonical entity families this connector can populate."""

    @abstractmethod
    def permission_manifest(self) -> PermissionManifest:
        """Least-privilege grants the customer must provision."""

    @abstractmethod
    def harvest(self) -> HarvestBundle:
        """Read metadata and return canonical entities. Must not mutate anything."""

    # -- helpers ------------------------------------------------------------ #

    def query(self, name: str) -> str:
        """Fetch a catalogued statement, re-validating it as read-only."""
        statement = self.query_catalog[name]
        return assert_read_only(statement, source=f"{self.key}.{name}")

    def api_call(self, name: str) -> str:
        """Fetch a catalogued API call, re-validating it as read-only."""
        call = self.api_catalog[name]
        return assert_read_only_api(
            call, source=f"{self.key}.{name}", allowed_post=self.read_only_post_endpoints
        )

    def preflight(self) -> list[str]:
        """Cheap configuration validation; returns human-readable problems."""
        return []

    def config_summary(self) -> dict[str, Any]:
        """Non-secret provenance recorded on the harvest run.

        This is persisted and shown to the customer, so a connector must return
        only settings that explain *how the estate was read* -- never an
        account, a user, a token or any other credential. The default is empty:
        a connector opts in to disclosing something.
        """
        return {}

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "platform": self.platform,
            "display_name": self.display_name,
            "capabilities": sorted(self.capabilities()),
            "permission_manifest": self.permission_manifest().to_dict(),
            "query_catalog": sorted(self.query_catalog),
            "api_catalog": sorted(self.api_catalog),
        }
