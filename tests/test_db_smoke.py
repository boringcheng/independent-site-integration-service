"""M0 心跳：证明"应用配置 + 真实 MySQL"这条链路是通的。

这不是走形式的健康检查——后续所有调度/锁相关的测试都建立在
"能连上真实 MySQL、并且隔离级别确实是 READ COMMITTED"之上。
"""

from __future__ import annotations

import pytest
from app.db import build_engine, ping
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.integration
def test_mysql_is_reachable(engine: Engine) -> None:
    assert ping(engine) is True


@pytest.mark.integration
def test_mysql_version_is_8(engine: Engine) -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar_one()
    assert str(version).startswith("8."), f"需要 MySQL 8.x，实际 {version}"


@pytest.mark.integration
def test_connection_is_read_committed(engine: Engine) -> None:
    with engine.connect() as conn:
        level = conn.exec_driver_sql("SELECT @@transaction_isolation").scalar_one()
    assert str(level).upper().replace("-", " ") == "READ COMMITTED"


@pytest.mark.integration
def test_build_engine_uses_read_committed(test_database_url: str) -> None:
    eng = build_engine(test_database_url, pool_size=1)
    try:
        with eng.connect() as conn:
            level = conn.exec_driver_sql("SELECT @@transaction_isolation").scalar_one()
        assert str(level).upper().replace("-", " ") == "READ COMMITTED"
    finally:
        eng.dispose()
