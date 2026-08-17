"""Check library. Importing this package registers every check."""

from eairn.checks import (  # noqa: F401  (imported for registration side effects)
    agent,
    ai_engineering,
    governance,
    metadata,
    quality,
    rag,
    security,
    semantic,
)
from eairn.checks.base import (  # noqa: F401
    REGISTRY,
    CheckSpec,
    Estate,
    EvidenceRecord,
    run_checks,
)

__all__ = ["REGISTRY", "CheckSpec", "Estate", "EvidenceRecord", "run_checks"]
