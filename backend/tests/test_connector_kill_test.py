"""CI kill test: connectors cannot write to a customer platform.

The blueprint makes this non-negotiable, so it is asserted mechanically rather
than by review: every catalogued statement must pass the read-only guard, every
catalogued API call must use a read-only method, and the guard itself must
reject the mutations it exists to reject.
"""

from __future__ import annotations

import pytest

from eairn.connectors import (
    ReadOnlyViolation,
    all_connectors,
    assert_read_only,
    assert_read_only_api,
)

MUTATIONS = [
    "DROP TABLE customers",
    "DELETE FROM orders WHERE 1=1",
    "UPDATE accounts SET balance = 0",
    "INSERT INTO audit VALUES (1)",
    "CREATE TABLE staging.copy AS SELECT * FROM customers",
    "TRUNCATE TABLE events",
    "GRANT SELECT ON DATABASE prod TO ROLE eairn",
    "MERGE INTO target USING source ON target.id = source.id",
    "ALTER TABLE orders ADD COLUMN x INT",
    "CALL admin.purge()",
    "SELECT 1; DROP TABLE customers",
    "WITH gone AS (DELETE FROM orders RETURNING id) SELECT * FROM gone",
]

READ_ONLY = [
    "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES WHERE DELETED IS NULL",
    "SELECT TABLE_NAME, LAST_ALTERED, ROW_COUNT FROM information_schema.tables",
    "WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "SHOW GRANTS TO ROLE EAIRN_READONLY",
    "SELECT owner, table_name, comments FROM dba_tab_comments",
    # Metadata columns whose names contain mutating verbs must not trip the guard.
    "SELECT DELETED, LAST_UPDATED, CREATED_ON, EXECUTION_TIME FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES",
]


@pytest.mark.parametrize("statement", MUTATIONS)
def test_guard_rejects_mutations(statement: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(statement)


@pytest.mark.parametrize("statement", READ_ONLY)
def test_guard_accepts_read_only(statement: str) -> None:
    assert assert_read_only(statement) == statement


def test_every_catalogued_statement_is_read_only() -> None:
    checked = 0
    for connector_cls in all_connectors():
        connector = connector_cls({})
        for name in connector.query_catalog:
            connector.query(name)  # raises ReadOnlyViolation on a mutating statement
            checked += 1
    assert checked > 0, "no connector queries were checked -- the kill test would be vacuous"


def test_every_catalogued_api_call_is_read_only() -> None:
    for connector_cls in all_connectors():
        connector = connector_cls({})
        for name in connector.api_catalog:
            connector.api_call(name)


def test_api_guard_rejects_writes() -> None:
    for call in ("PUT https://example.test/api/item", "DELETE https://example.test/api/item"):
        with pytest.raises(ReadOnlyViolation):
            assert_read_only_api(call)
    with pytest.raises(ReadOnlyViolation):
        # POST is only accepted for endpoints explicitly reviewed as read-only.
        assert_read_only_api("POST https://example.test/api/item")
    assert assert_read_only_api(
        "POST https://example.test/search", allowed_post=("https://example.test/search",)
    )


def test_no_connector_requests_row_data() -> None:
    for connector_cls in all_connectors():
        manifest = connector_cls({}).permission_manifest()
        assert manifest.reads_row_data is False, f"{connector_cls.key} declares row-data access"


def test_snowflake_refuses_admin_roles() -> None:
    from eairn.connectors.snowflake import SnowflakeConnector

    problems = SnowflakeConnector(
        {
            "account": "acct",
            "user": "svc",
            "role": "ACCOUNTADMIN",
            "warehouse": "wh",
            "password": "x",
        }
    ).preflight()
    assert any("least-privilege" in p for p in problems)
