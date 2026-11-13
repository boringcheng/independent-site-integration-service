"""数据库连接工厂。

为什么连接级隔离级别固定为 READ COMMITTED？

- 调度逻辑依赖"拿到行锁后重新读取能看到别人刚提交的状态"；
- MySQL 默认的 REPEATABLE READ 会在事务开始时固定快照，
  两个 worker 可能都认为队首任务仍是 PENDING。

这个选择会在 ADR-0001 中记录，改它必须先改 ADR。
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings


def build_engine(url: str | None = None, *, pool_size: int = 10) -> Engine:
    return create_engine(
        url or get_settings().database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=pool_size * 2,
        isolation_level="READ COMMITTED",
        future=True,
    )


def ping(engine: Engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
