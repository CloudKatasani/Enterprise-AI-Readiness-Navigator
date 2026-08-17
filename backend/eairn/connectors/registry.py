"""Connector registry: the plugin surface the pipeline and API resolve against."""

from __future__ import annotations

from typing import Any, Iterable

from eairn.connectors.base import Connector
from eairn.connectors.demo import DemoConnector
from eairn.connectors.platforms import (
    BigQueryConnector,
    BundleBackedConnector,
    DatabricksConnector,
    FabricConnector,
    OracleConnector,
)
from eairn.connectors.snowflake import SnowflakeConnector
from eairn.connectors.tools import (
    AlationConnector,
    AtaccamaConnector,
    AtlanConnector,
    CollibraConnector,
    GreatExpectationsConnector,
    InformaticaCDGCConnector,
    MonteCarloConnector,
    PurviewConnector,
    SodaConnector,
)

_CONNECTORS: tuple[type[Connector], ...] = (
    DemoConnector,
    SnowflakeConnector,
    DatabricksConnector,
    FabricConnector,
    BigQueryConnector,
    OracleConnector,
    CollibraConnector,
    AlationConnector,
    PurviewConnector,
    AtlanConnector,
    InformaticaCDGCConnector,
    MonteCarloConnector,
    GreatExpectationsConnector,
    SodaConnector,
    AtaccamaConnector,
)

REGISTRY: dict[str, type[Connector]] = {cls.key: cls for cls in _CONNECTORS}


def get_connector_class(key: str) -> type[Connector]:
    try:
        return REGISTRY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown connector {key!r}. Available: {', '.join(sorted(REGISTRY))}") from exc


def build_connector(key: str, config: dict[str, Any] | None = None) -> Connector:
    return get_connector_class(key)(config or {})


def all_connectors() -> Iterable[type[Connector]]:
    return _CONNECTORS


def describe_all() -> list[dict[str, Any]]:
    """Catalog for the Portal's connector page and the customer permission pack."""
    described = []
    for cls in _CONNECTORS:
        instance = cls({})
        payload = instance.describe()
        payload["live_harvest_available"] = not issubclass(cls, BundleBackedConnector)
        payload["roadmap_phase"] = getattr(cls, "roadmap_phase", "P1")
        payload["accepts_canonical_bundle"] = issubclass(cls, BundleBackedConnector)
        described.append(payload)
    return described
