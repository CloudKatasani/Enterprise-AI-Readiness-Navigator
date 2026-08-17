from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Point every test at a throwaway SQLite file before eairn.db imports settings.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="eairn-tests-"))
os.environ.setdefault("EAIRN_DATABASE_URL", f"sqlite:///{_TMP_DIR / 'test.db'}")
os.environ.pop("EAIRN_ANTHROPIC_API_KEY", None)

from eairn.benchmarks import install_cohorts  # noqa: E402
from eairn.config import get_settings  # noqa: E402
from eairn.db import init_db, session_scope  # noqa: E402
from eairn.models import Tenant  # noqa: E402
from eairn.pipeline import run_assessment  # noqa: E402
from eairn.rubric import get_rubric, install_rubric  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    init_db()
    with session_scope() as session:
        if get_rubric(session, get_settings().default_rubric_version) is None:
            install_rubric(session, get_settings().default_rubric_version)
        install_cohorts(session)


@pytest.fixture(scope="session")
def demo_tenant_key(_database) -> str:
    with session_scope() as session:
        tenant = Tenant(
            key="test-tenant",
            name="Test Estate",
            industry="financial_services",
            size_band="enterprise",
        )
        session.add(tenant)
        session.flush()
        return tenant.key


@pytest.fixture(scope="session")
def demo_snapshot(demo_tenant_key) -> str:
    from sqlalchemy import select

    with session_scope() as session:
        tenant = session.scalar(select(Tenant).where(Tenant.key == demo_tenant_key))
        assessment = run_assessment(session, tenant, [("demo", {})], label="test run")
        return assessment.snapshot_id
