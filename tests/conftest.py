"""pytest 全局夹具。

测试默认连接本机 Docker MySQL 的独立测试库 ``shopify_shopline_test``；
CI 中由 service container 提供，并通过 ``TEST_DATABASE_URL`` 覆盖。

约定：
- 需要真实数据库的测试必须标 ``@pytest.mark.integration``；
- 数据库不可用时本地跳过，CI 设 ``REQUIRE_DB=1`` 后直接失败，
  避免"测试全绿但其实没连数据库"。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_TEST_URL = (
    "mysql+pymysql://app:app_pass@127.0.0.1:3306/shopify_shopline_test?charset=utf8mb4"
)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_URL)


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    eng = create_engine(
        test_database_url,
        pool_pre_ping=True,
        isolation_level="READ COMMITTED",
    )
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        if os.getenv("REQUIRE_DB") == "1":
            pytest.fail(f"数据库不可用（REQUIRE_DB=1）: {exc}")
        pytest.skip(f"数据库不可用，跳过集成测试: {exc}")
    yield eng
    eng.dispose()
