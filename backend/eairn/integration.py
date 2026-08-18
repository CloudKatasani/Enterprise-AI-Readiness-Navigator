"""API Documentation view: how a deployment replaces the demo estate with a real one.

The Connectors page publishes the *permission* pack -- what EAIRN asks a customer
to grant before anything is connected. This view answers the next question, the
integrator's one: given that grant, what do I actually configure, what does the
runtime call, where must it be allowed to reach, and which parts of the score
light up as a result?

Three sources are merged, and the split is deliberate:

* **The connector registry** supplies everything structural -- capabilities, the
  permission manifest, and the verbatim statement and endpoint catalogs. It is
  read live, so this page cannot document an endpoint the code does not issue.
* **``integration_v1.yaml``** supplies the operational detail -- auth modes,
  configuration keys, egress hosts, freshness and paging. Data rather than code,
  so a deployment can correct a hostname without an engine change.
* **The check library** supplies consequence: which checks a connector's
  capabilities unlock, and which stay unmeasured without it.

Every catalogued statement and call is re-validated through the read-only guard
as it is rendered. The page therefore *demonstrates* the read-only guarantee
rather than asserting it: a mutating statement could not be documented here, for
the same reason it could not be executed.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from eairn.checks import REGISTRY as CHECK_REGISTRY
from eairn.config import SEED_DIR, Settings
from eairn.connectors.base import ReadOnlyViolation, assert_read_only, assert_read_only_api
from eairn.connectors.registry import all_connectors
from eairn.models import Rubric

GUIDE_VERSION = "1"


def guide_path(version: str = GUIDE_VERSION) -> Path:
    return SEED_DIR / f"integration_v{version}.yaml"


@lru_cache(maxsize=4)
def load_guide(version: str = GUIDE_VERSION) -> dict[str, Any]:
    path = guide_path(version)
    if not path.exists():
        raise FileNotFoundError(f"No integration guide for version {version} at {path}")
    with path.open("r", encoding="utf-8") as fh:
        guide = yaml.safe_load(fh)
    guide["source_digest"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return guide


def _squash(statement: str) -> str:
    """Normalise a triple-quoted SQL literal for display without altering it."""
    lines = [line.rstrip() for line in statement.strip("\n").rstrip().splitlines()]
    if not lines:
        return ""
    indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return "\n".join(line[indent:] if len(line) >= indent else line for line in lines)


def _verified_calls(cls: type) -> tuple[list[dict[str, Any]], list[str]]:
    """Catalogued statements and endpoints, each re-checked as read-only.

    A guard failure is surfaced as a problem rather than raised: the page's job
    is to show the reader that the guarantee holds, which means it also has to be
    able to show them when it does not.
    """
    entries: list[dict[str, Any]] = []
    problems: list[str] = []

    for name, statement in sorted(cls.query_catalog.items()):
        try:
            assert_read_only(statement, source=f"{cls.key}.{name}")
            verified = True
        except ReadOnlyViolation as exc:
            verified = False
            problems.append(str(exc))
        entries.append(
            {"name": name, "kind": "sql", "statement": _squash(statement), "read_only_verified": verified}
        )

    for name, call in sorted(cls.api_catalog.items()):
        try:
            assert_read_only_api(call, source=f"{cls.key}.{name}", allowed_post=cls.read_only_post_endpoints)
            verified = True
        except ReadOnlyViolation as exc:
            verified = False
            problems.append(str(exc))
        method, _, url = call.partition(" ")
        entries.append(
            {
                "name": name,
                "kind": "http",
                "method": method,
                "statement": url.strip(),
                "read_only_verified": verified,
                # A POST that only reads still has to be reviewed as one; say so
                # in the place a reader would otherwise assume a mutation.
                "reviewed_read_only_post": url.strip() in set(cls.read_only_post_endpoints),
            }
        )

    return entries, problems


def _pillar_names(rubric: Rubric | None) -> dict[str, str]:
    if rubric is None:
        return {}
    return {pillar.key: pillar.name for pillar in rubric.pillars}


def _checks_for(capabilities: set[str], pillar_names: dict[str, str]) -> dict[str, Any]:
    """Which checks these capabilities unlock, and which they leave unmeasured."""
    unlocked: dict[str, list[dict[str, str]]] = {}
    blocked: list[dict[str, Any]] = []
    for spec in sorted(CHECK_REGISTRY.values(), key=lambda s: s.check_id):
        entry = {"check_id": spec.check_id, "title": spec.title}
        if spec.requires <= capabilities:
            unlocked.setdefault(spec.pillar_key, []).append(entry)
        else:
            blocked.append({**entry, "missing": sorted(spec.requires - capabilities)})
    return {
        "unlocked_count": sum(len(v) for v in unlocked.values()),
        "blocked_count": len(blocked),
        "by_pillar": [
            {
                "pillar_key": key,
                "pillar_name": pillar_names.get(key, key.replace("_", " ").title()),
                "checks": checks,
            }
            for key, checks in sorted(unlocked.items())
        ],
        "still_unmeasured": blocked,
    }


def _capability_matrix(pillar_names: dict[str, str]) -> list[dict[str, Any]]:
    """Capability -> the connectors that supply it and the checks that need it.

    Read this column-first when scoping a rollout: it answers "which platform do
    I have to connect before RG-005 stops reporting as not measured", which is
    the question a coverage gap actually raises.
    """
    providers: dict[str, list[str]] = {}
    for cls in all_connectors():
        for capability in cls({}).capabilities():
            providers.setdefault(capability, []).append(cls.key)

    consumers: dict[str, list[dict[str, str]]] = {}
    for spec in sorted(CHECK_REGISTRY.values(), key=lambda s: s.check_id):
        for capability in spec.requires:
            consumers.setdefault(capability, []).append(
                {
                    "check_id": spec.check_id,
                    "pillar_key": spec.pillar_key,
                    "pillar_name": pillar_names.get(
                        spec.pillar_key, spec.pillar_key.replace("_", " ").title()
                    ),
                }
            )

    return [
        {
            "capability": capability,
            "connectors": sorted(providers.get(capability, [])),
            "checks": consumers.get(capability, []),
            "check_count": len(consumers.get(capability, [])),
        }
        for capability in sorted(set(providers) | set(consumers))
    ]


def _connector_entry(cls: type, content: dict[str, Any], pillar_names: dict[str, str]) -> dict[str, Any]:
    from eairn.connectors.platforms import BundleBackedConnector

    instance = cls({})
    capabilities = instance.capabilities()
    calls, problems = _verified_calls(cls)
    entry = content.get(cls.key, {})

    return {
        "key": cls.key,
        "platform": cls.platform,
        "display_name": cls.display_name,
        "capabilities": sorted(capabilities),
        "roadmap_phase": getattr(cls, "roadmap_phase", "P1"),
        "live_harvest_available": not issubclass(cls, BundleBackedConnector),
        "accepts_canonical_bundle": issubclass(cls, BundleBackedConnector),
        "live_driver": getattr(cls, "live_driver", ""),
        "permission_manifest": instance.permission_manifest().to_dict(),
        "calls": calls,
        "read_only_problems": problems,
        "coverage": _checks_for(capabilities, pillar_names),
        # Content from the guide. Absent keys render as empty rather than
        # failing: a newly registered connector should appear here undocumented,
        # not disappear.
        "summary": entry.get("summary", ""),
        "vendor_docs": entry.get("vendor_docs", []),
        "auth": entry.get("auth", []),
        "config_fields": entry.get("config_fields", []),
        "egress": entry.get("egress", []),
        "freshness": entry.get("freshness", ""),
        "pagination": entry.get("pagination", ""),
        "limits": entry.get("limits", ""),
        "preconditions": entry.get("preconditions", []),
        "documented": cls.key in content,
    }


def integration_guide(rubric: Rubric | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """The API Documentation view: registry contract + operational wiring detail."""
    guide = load_guide()
    content = guide.get("connectors") or {}
    pillar_names = _pillar_names(rubric)

    connectors = [_connector_entry(cls, content, pillar_names) for cls in all_connectors()]
    # Live drivers first, then by roadmap phase: the reader deciding what to
    # connect this quarter wants the ready ones at the top.
    connectors.sort(key=lambda c: (not c["live_harvest_available"], c["roadmap_phase"], c["key"]))

    hosting = dict(guide.get("hosting") or {})
    if settings is not None:
        # Show the live default next to each documented variable, so a reader can
        # tell a configured value from a fallback without reading the source.
        defaults = {
            "EAIRN_DATABASE_URL": _redact_url(settings.database_url),
            "EAIRN_DEFAULT_RUBRIC_VERSION": settings.default_rubric_version,
            "EAIRN_CONFIDENCE_THRESHOLD": f"{settings.confidence_threshold}",
            "EAIRN_ALLOW_ROW_SAMPLING": str(settings.allow_row_sampling).lower(),
            "EAIRN_ANTHROPIC_API_KEY": "set" if settings.anthropic_api_key else "unset",
            "EAIRN_CORS_ORIGINS": settings.cors_origins,
        }
        environment = dict(hosting.get("environment") or {})
        environment["variables"] = [
            {**variable, "current": defaults.get(variable["name"], "")}
            for variable in environment.get("variables", [])
        ]
        hosting["environment"] = environment

    return {
        "guide_version": guide.get("version", GUIDE_VERSION),
        "guide_digest": guide.get("source_digest", ""),
        "intro": guide.get("intro", {}),
        "hosting": hosting,
        "canonical_bundle": guide.get("canonical_bundle", {}),
        "connectors": connectors,
        "capability_matrix": _capability_matrix(pillar_names),
        "totals": {
            "connectors": len(connectors),
            "live_drivers": sum(1 for c in connectors if c["live_harvest_available"]),
            "bundle_backed": sum(1 for c in connectors if c["accepts_canonical_bundle"]),
            "documented_calls": sum(len(c["calls"]) for c in connectors),
            "registered_checks": len(CHECK_REGISTRY),
            # Zero is the only acceptable value, and it is asserted in CI. It is
            # published rather than assumed because "we validate this" is a
            # weaker claim than a number the reader can watch.
            "read_only_violations": sum(len(c["read_only_problems"]) for c in connectors),
        },
    }


def _redact_url(url: str) -> str:
    """Strip any password from a database URL before it is displayed."""
    if "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    if "@" not in rest:
        return url
    credentials, _, host = rest.rpartition("@")
    user, _, password = credentials.partition(":")
    return f"{scheme}://{user}{':***' if password else ''}@{host}"
